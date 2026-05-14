from __future__ import annotations

import copy
import os
from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.webhook import WebhookEndpoint
from app.models.workflows import Workflow
from app.models.workflow_versions import WorkflowVersion
from app.schemas.workflows import WorkflowCreate, WorkflowUpdate

PUBLISHED_RUN_NODE_ID = "__published_run__"
PUBLISHED_RUN_PATH_HINT = "published-run"
WORKFLOW_TRIGGER_NODE_TYPES = {
    "manual_trigger",
    "form_trigger",
    "schedule_trigger",
    "webhook_trigger",
    "workflow_trigger",
}

PUBLISHED_WORKFLOW_EDIT_ERROR = "Published workflows cannot be edited. Unpublish first."
INACTIVE_WORKFLOW_PUBLISH_ERROR = "Inactive workflows cannot be published. Activate workflow first."


class PublishedWorkflowEditError(ValueError):
    """Raised when a locked published workflow receives a normal update."""


class InactiveWorkflowPublishError(ValueError):
    """Raised when an inactive workflow is sent to the publish endpoint."""


class WorkflowService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_workflow(self, *, user_id: UUID, payload: WorkflowCreate) -> Workflow:
        definition = self._sanitize_definition_for_storage(
            payload.definition.model_dump(mode="python")
        )
        workflow = Workflow(
            user_id=user_id,
            name=payload.name,
            description=payload.description,
            definition=definition,
            is_published=False,
            is_active=True,
        )
        self.db.add(workflow)
        await self.db.commit()
        await self._ensure_webhook_endpoints(workflow)
        await self.db.refresh(workflow)
        return workflow

    async def list_workflows(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        total = await self.db.scalar(
            select(func.count()).select_from(Workflow).where(Workflow.user_id == user_id)
        )
        result = await self.db.execute(
            select(
                Workflow.id.label("id"),
                Workflow.user_id.label("user_id"),
                Workflow.name.label("name"),
                Workflow.description.label("description"),
                Workflow.is_published.label("is_published"),
                Workflow.is_active.label("is_active"),
                Workflow.created_at.label("created_at"),
                Workflow.updated_at.label("updated_at"),
            )
            .where(Workflow.user_id == user_id)
            .order_by(Workflow.updated_at.desc(), Workflow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = result.mappings().all()
        return int(total or 0), [dict(row) for row in rows]

    async def get_workflow(self, *, workflow_id: UUID, user_id: UUID) -> Workflow | None:
        result = await self.db.scalar(
            select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == user_id)
        )
        return result

    async def update_workflow(
        self,
        *,
        workflow_id: UUID,
        user_id: UUID,
        payload: WorkflowUpdate,
    ) -> Workflow | None:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return None
        if workflow.is_published:
            raise PublishedWorkflowEditError(PUBLISHED_WORKFLOW_EDIT_ERROR)

        updates = payload.model_dump(exclude_unset=True, mode="python")
        # Publish state is controlled exclusively by publish/unpublish endpoints so
        # locking, timestamps, and webhook activation stay consistent.
        updates.pop("is_published", None)
        if "definition" in updates and updates["definition"] is not None:
            updates["definition"] = self._sanitize_definition_for_storage(
                payload.definition.model_dump(mode="python")
            )

        for field, value in updates.items():
            setattr(workflow, field, value)

        await self.db.commit()
        await self._ensure_webhook_endpoints(workflow)
        await self.db.refresh(workflow)
        return workflow

    async def publish_workflow(self, *, workflow_id: UUID, user_id: UUID) -> Workflow | None:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return None
        if not bool(getattr(workflow, "is_active", True)):
            raise InactiveWorkflowPublishError(INACTIVE_WORKFLOW_PUBLISH_ERROR)

        if not workflow.is_published:
            workflow.is_published = True
            workflow.published_at = datetime.now(timezone.utc)

        await self.db.execute(
            update(WebhookEndpoint)
            .where(WebhookEndpoint.workflow_id == workflow.id)
            .values(is_active=True)
        )
        await self.db.commit()
        await self._ensure_webhook_endpoints(workflow)
        await self.db.refresh(workflow)
        return workflow

    async def unpublish_workflow(self, *, workflow_id: UUID, user_id: UUID) -> Workflow | None:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return None

        workflow.is_published = False
        workflow.published_at = None
        await self.db.execute(
            update(WebhookEndpoint)
            .where(WebhookEndpoint.workflow_id == workflow.id)
            .values(is_active=False)
        )
        await self.db.commit()
        await self._ensure_webhook_endpoints(workflow)
        await self.db.refresh(workflow)
        return workflow

    async def delete_workflow(self, *, workflow_id: UUID, user_id: UUID) -> bool:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return False

        await self.db.delete(workflow)
        await self.db.commit()
        return True

    async def create_workflow_version(
        self,
        *,
        workflow_id: UUID,
        user_id: UUID,
        note: str | None = None,
    ) -> WorkflowVersion | None:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return None

        normalized_note = note.strip() if isinstance(note, str) and note.strip() else None
        for _ in range(3):
            current_max_version = await self.db.scalar(
                select(func.max(WorkflowVersion.version_number)).where(
                    WorkflowVersion.workflow_id == workflow.id
                )
            )
            next_version_number = int(current_max_version or 0) + 1

            version = WorkflowVersion(
                workflow_id=workflow.id,
                created_by=user_id,
                version_number=next_version_number,
                snapshot_json=self._build_version_snapshot(workflow),
                note=normalized_note,
            )
            self.db.add(version)
            try:
                await self.db.commit()
            except IntegrityError:
                await self.db.rollback()
                continue
            await self.db.refresh(version)
            return version

        raise RuntimeError("Failed to allocate workflow version number after retries")

    async def list_workflow_versions(
        self,
        *,
        workflow_id: UUID,
        user_id: UUID,
    ) -> list[WorkflowVersion] | None:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return None

        result = await self.db.scalars(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow.id)
            .order_by(WorkflowVersion.version_number.desc(), WorkflowVersion.created_at.desc())
        )
        return list(result.all())

    async def get_workflow_version(
        self,
        *,
        workflow_id: UUID,
        version_id: UUID,
        user_id: UUID,
    ) -> WorkflowVersion | None:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return None

        return await self.db.scalar(
            select(WorkflowVersion).where(
                WorkflowVersion.id == version_id,
                WorkflowVersion.workflow_id == workflow.id,
            )
        )

    async def restore_workflow_version(
        self,
        *,
        workflow_id: UUID,
        version_id: UUID,
        user_id: UUID,
    ) -> Workflow | None:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return None
        if workflow.is_published:
            raise PublishedWorkflowEditError(PUBLISHED_WORKFLOW_EDIT_ERROR)

        version = await self.db.scalar(
            select(WorkflowVersion).where(
                WorkflowVersion.id == version_id,
                WorkflowVersion.workflow_id == workflow.id,
            )
        )
        if version is None:
            return None

        snapshot = version.snapshot_json if isinstance(version.snapshot_json, dict) else {}
        snapshot_name = snapshot.get("name")
        snapshot_definition = snapshot.get("definition")
        if isinstance(snapshot_name, str) and snapshot_name.strip():
            workflow.name = snapshot_name.strip()
        snapshot_description = snapshot.get("description")
        workflow.description = (
            snapshot_description if isinstance(snapshot_description, str) else None
        )
        if isinstance(snapshot_definition, dict):
            workflow.definition = self._sanitize_definition_for_storage(
                copy.deepcopy(snapshot_definition)
            )

        await self.db.commit()
        await self._ensure_webhook_endpoints(workflow)
        await self.db.refresh(workflow)
        return workflow

    async def get_webhook_endpoints(
        self,
        *,
        workflow_id: UUID,
        user_id: UUID,
        base_url: str,
    ) -> list[dict[str, Any]]:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return []

        webhook_rows = (
            await self.db.scalars(
                select(WebhookEndpoint).where(WebhookEndpoint.workflow_id == workflow.id)
            )
        ).all()
        rows_by_node_id = {row.node_id: row for row in webhook_rows}
        if not rows_by_node_id:
            return []

        stripped_base = base_url.rstrip("/")
        webhooks: list[dict[str, Any]] = []
        for node in workflow.definition.get("nodes", []):
            if node.get("type") != "webhook_trigger":
                continue
            node_id = str(node.get("id") or "")
            row = rows_by_node_id.get(node_id)
            if row is None:
                continue

            config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
            method = str(config.get("method") or "POST").upper()
            path = str(config.get("path") or "").lstrip("/")

            webhooks.append(
                {
                    "node_id": node_id,
                    "path_token": row.path_token,
                    "is_active": bool(row.is_active),
                    "method": method,
                    "path": path,
                    "url": f"{stripped_base}/webhook/{row.path_token}",
                }
            )

        return webhooks

    async def get_public_run_endpoint(
        self,
        *,
        workflow_id: UUID,
        user_id: UUID,
        base_url: str,
        frontend_base_url: str | None = None,
    ) -> dict[str, Any] | None:
        workflow = await self.get_workflow(workflow_id=workflow_id, user_id=user_id)
        if workflow is None:
            return None
        has_trigger_node = any(
            node.get("type") in WORKFLOW_TRIGGER_NODE_TYPES
            for node in workflow.definition.get("nodes", [])
            if isinstance(node, dict)
        )
        if not has_trigger_node:
            await self._ensure_webhook_endpoints(workflow)
            return None

        row = await self.db.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.workflow_id == workflow.id,
                WebhookEndpoint.node_id == PUBLISHED_RUN_NODE_ID,
            )
        )
        if row is None:
            await self._ensure_webhook_endpoints(workflow)
            row = await self.db.scalar(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.workflow_id == workflow.id,
                    WebhookEndpoint.node_id == PUBLISHED_RUN_NODE_ID,
                )
            )
        if row is None:
            return None

        stripped_base = base_url.rstrip("/")
        form_node = self._resolve_form_trigger_node(workflow.definition)
        if form_node is not None:
            frontend_base = str(
                os.getenv("FRONTEND_BASE_URL") or frontend_base_url or stripped_base
            ).rstrip("/")
            return {
                "node_id": row.node_id,
                "path_token": row.path_token,
                "is_active": bool(row.is_active),
                "method": "GET",
                "path": f"public/forms/{row.path_token}",
                "url": f"{frontend_base}/public/forms/{row.path_token}",
            }

        return {
            "node_id": row.node_id,
            "path_token": row.path_token,
            "is_active": bool(row.is_active),
            "method": "GET",
            "path": PUBLISHED_RUN_PATH_HINT,
            "url": f"{stripped_base}/webhook/{row.path_token}",
        }

    async def _ensure_webhook_endpoints(self, workflow: Workflow) -> None:
        trigger_node_ids = {
            node["id"]
            for node in workflow.definition.get("nodes", [])
            if node.get("type") == "webhook_trigger"
        }
        if any(
            node.get("type") in WORKFLOW_TRIGGER_NODE_TYPES
            for node in workflow.definition.get("nodes", [])
            if isinstance(node, dict)
        ):
            trigger_node_ids.add(PUBLISHED_RUN_NODE_ID)

        existing = (
            await self.db.scalars(
                select(WebhookEndpoint).where(WebhookEndpoint.workflow_id == workflow.id)
            )
        ).all()
        existing_by_node_id = {webhook.node_id: webhook for webhook in existing}

        for node_id in trigger_node_ids:
            if node_id in existing_by_node_id:
                existing_by_node_id[node_id].is_active = workflow.is_published
                continue
            self.db.add(
                WebhookEndpoint(
                    workflow_id=workflow.id,
                    user_id=workflow.user_id,
                    node_id=node_id,
                    path_token=token_urlsafe(16),
                    is_active=workflow.is_published,
                )
            )

        for node_id, webhook in existing_by_node_id.items():
            if node_id in trigger_node_ids:
                continue
            webhook.is_active = False

        await self.db.commit()

    @staticmethod
    def _resolve_form_trigger_node(definition: dict[str, Any]) -> dict[str, Any] | None:
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])
        form_nodes = [
            node
            for node in nodes
            if isinstance(node, dict) and node.get("type") == "form_trigger"
        ]
        if not form_nodes:
            return None

        indegree = {
            str(node.get("id")): 0
            for node in nodes
            if isinstance(node, dict) and node.get("id")
        }
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            target = str(edge.get("target") or "")
            if target in indegree:
                indegree[target] += 1

        for node in form_nodes:
            node_id = str(node.get("id") or "")
            if node_id and indegree.get(node_id, 0) == 0:
                return node
        return form_nodes[0]

    @staticmethod
    def _build_version_snapshot(workflow: Workflow) -> dict[str, Any]:
        return {
            "name": workflow.name,
            "description": workflow.description,
            "definition": copy.deepcopy(workflow.definition),
        }

    @staticmethod
    def _sanitize_definition_for_storage(definition: dict[str, Any]) -> dict[str, Any]:
        sanitized_nodes: list[dict[str, Any]] = []
        for node in definition.get("nodes", []):
            if not isinstance(node, dict):
                continue

            node_copy = dict(node)
            if node_copy.get("type") == "telegram" and isinstance(node_copy.get("config"), dict):
                config = dict(node_copy["config"])
                config.pop("bot_token", None)
                config.pop("chat_id", None)
                node_copy["config"] = config
            if node_copy.get("type") in {"get_gmail_message", "send_gmail_message", "create_gmail_draft", "add_gmail_label"} and isinstance(node_copy.get("config"), dict):
                config = dict(node_copy["config"])
                config.pop("app_password", None)
                config.pop("password", None)
                config.pop("api_key", None)
                config.pop("email", None)
                config.pop("user_email", None)
                config.pop("username", None)
                node_copy["config"] = config
            if node_copy.get("type") in {"create_google_sheets", "read_google_sheets", "search_update_google_sheets"} and isinstance(node_copy.get("config"), dict):
                config = dict(node_copy["config"])
                config.pop("service_account_json", None)
                config.pop("serviceAccountJson", None)
                config.pop("private_key", None)
                config.pop("privateKey", None)
                node_copy["config"] = config
            if node_copy.get("type") in {"create_google_docs", "read_google_docs", "update_google_docs"} and isinstance(node_copy.get("config"), dict):
                config = dict(node_copy["config"])
                config.pop("service_account_json", None)
                config.pop("serviceAccountJson", None)
                config.pop("private_key", None)
                config.pop("privateKey", None)
                node_copy["config"] = config
            if node_copy.get("type") == "slack_send_message" and isinstance(node_copy.get("config"), dict):
                config = dict(node_copy["config"])
                config.pop("webhook_url", None)
                config.pop("channel", None)
                node_copy["config"] = config
            sanitized_nodes.append(node_copy)

        raw_loop_control = definition.get("loop_control")
        if isinstance(raw_loop_control, dict):
            loop_control = {
                "enabled": bool(raw_loop_control.get("enabled", False)),
                "max_node_executions": int(raw_loop_control.get("max_node_executions", 3) or 3),
                "max_total_node_executions": int(
                    raw_loop_control.get("max_total_node_executions", 500) or 500
                ),
            }
        else:
            loop_control = {
                "enabled": False,
                "max_node_executions": 3,
                "max_total_node_executions": 500,
            }

        # Keep safety caps valid even if client sent bad values.
        loop_control["max_node_executions"] = max(1, int(loop_control["max_node_executions"]))
        loop_control["max_total_node_executions"] = max(
            1, int(loop_control["max_total_node_executions"])
        )

        return {
            "nodes": sanitized_nodes,
            "edges": list(definition.get("edges", [])),
            "loop_control": loop_control,
        }
