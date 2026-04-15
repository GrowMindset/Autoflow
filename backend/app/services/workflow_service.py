from __future__ import annotations

from secrets import token_urlsafe
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookEndpoint
from app.models.workflows import Workflow
from app.schemas.workflows import WorkflowCreate, WorkflowUpdate


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
    ) -> tuple[int, list[Workflow]]:
        total = await self.db.scalar(
            select(func.count()).select_from(Workflow).where(Workflow.user_id == user_id)
        )
        result = await self.db.scalars(
            select(Workflow)
            .where(Workflow.user_id == user_id)
            .order_by(Workflow.updated_at.desc(), Workflow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return int(total or 0), list(result.all())

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

        updates = payload.model_dump(exclude_unset=True, mode="python")
        if "definition" in updates and updates["definition"] is not None:
            updates["definition"] = self._sanitize_definition_for_storage(
                payload.definition.model_dump(mode="python")
            )

        for field, value in updates.items():
            setattr(workflow, field, value)

        if updates.get("is_published") is False:
            await self.db.execute(
                update(WebhookEndpoint)
                .where(WebhookEndpoint.workflow_id == workflow.id)
                .values(is_active=False)
            )
        elif updates.get("is_published") is True:
            await self.db.execute(
                update(WebhookEndpoint)
                .where(WebhookEndpoint.workflow_id == workflow.id)
                .values(is_active=True)
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

    async def _ensure_webhook_endpoints(self, workflow: Workflow) -> None:
        trigger_node_ids = {
            node["id"]
            for node in workflow.definition.get("nodes", [])
            if node.get("type") == "webhook_trigger"
        }

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
            if node_copy.get("type") in {"get_gmail_message", "send_gmail_message"} and isinstance(node_copy.get("config"), dict):
                config = dict(node_copy["config"])
                config.pop("app_password", None)
                config.pop("password", None)
                config.pop("api_key", None)
                config.pop("email", None)
                config.pop("user_email", None)
                config.pop("username", None)
                node_copy["config"] = config
            if node_copy.get("type") in {"create_google_sheets", "search_update_google_sheets"} and isinstance(node_copy.get("config"), dict):
                config = dict(node_copy["config"])
                config.pop("service_account_json", None)
                config.pop("serviceAccountJson", None)
                config.pop("private_key", None)
                config.pop("privateKey", None)
                node_copy["config"] = config
            if node_copy.get("type") in {"create_google_docs", "update_google_docs"} and isinstance(node_copy.get("config"), dict):
                config = dict(node_copy["config"])
                config.pop("service_account_json", None)
                config.pop("serviceAccountJson", None)
                config.pop("private_key", None)
                config.pop("privateKey", None)
                node_copy["config"] = config
            sanitized_nodes.append(node_copy)

        return {
            "nodes": sanitized_nodes,
            "edges": list(definition.get("edges", [])),
        }
