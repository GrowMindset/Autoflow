from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.error_messages import to_user_friendly_error_message
from app.execution.constants import MANUAL_STOP_ERROR_MESSAGE
from app.models.executions import Execution
from app.models.nodes_executions import NodeExecution
from app.models.user import User
from app.models.webhook import WebhookEndpoint
from app.models.workflows import Workflow
from app.schemas.executions import ExecutionStatus, TriggeredBy
from app.services.workflow_service import PUBLISHED_RUN_NODE_ID
from app.services.schedule_service import is_schedule_enabled, next_schedule_run_at
from app.tasks.execute_workflow import run_execution, run_node_test
from celery_config import WORKFLOW_EXECUTION_QUEUE, WORKFLOW_NODE_TEST_QUEUE

APP_TIMEZONE = ZoneInfo("Asia/Kolkata")
WORKFLOW_INACTIVE_ERROR_MESSAGE = "Workflow is inactive. Please activate workflow first."


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _ensure_workflow_is_active(workflow: Workflow) -> None:
        if bool(getattr(workflow, "is_active", True)):
            return
        raise ValueError(WORKFLOW_INACTIVE_ERROR_MESSAGE)

    async def create_manual_execution(
        self,
        *,
        workflow_id: UUID,
        user: User,
        start_node_id: str | None = None,
        loop_control_override: dict[str, Any] | None = None,
    ) -> Execution:
        await self._mark_stale_running_executions(user_id=user.id)

        workflow = await self._get_owned_workflow(workflow_id=workflow_id, user_id=user.id)
        if workflow is None:
            raise ValueError("Workflow not found")
        self._ensure_workflow_is_active(workflow)

        start_node_id = self._resolve_start_node_id(
            definition=workflow.definition,
            expected_types={"manual_trigger"},
            preferred_node_id=start_node_id,
        )
        return await self._create_and_enqueue_execution(
            workflow=workflow,
            user=user,
            triggered_by="manual",
            initial_payload=None,
            start_node_id=start_node_id,
            loop_control_override=loop_control_override,
        )

    async def create_form_execution(
        self,
        *,
        workflow_id: UUID,
        user: User,
        form_data: dict[str, Any],
        start_node_id: str | None = None,
        loop_control_override: dict[str, Any] | None = None,
    ) -> Execution:
        await self._mark_stale_running_executions(user_id=user.id)

        workflow = await self._get_owned_workflow(workflow_id=workflow_id, user_id=user.id)
        if workflow is None:
            raise ValueError("Workflow not found")
        self._ensure_workflow_is_active(workflow)

        start_node_id = self._resolve_start_node_id(
            definition=workflow.definition,
            expected_types={"form_trigger"},
            preferred_node_id=start_node_id,
        )
        return await self._create_and_enqueue_execution(
            workflow=workflow,
            user=user,
            triggered_by="form",
            initial_payload=form_data,
            start_node_id=start_node_id,
            loop_control_override=loop_control_override,
        )

    async def create_schedule_execution(
        self,
        *,
        workflow_id: UUID,
        user: User,
        start_node_id: str | None = None,
        schedule_payload: dict[str, Any] | None = None,
        require_published: bool = False,
        respect_schedule: bool = False,
        loop_control_override: dict[str, Any] | None = None,
    ) -> Execution:
        await self._mark_stale_running_executions(user_id=user.id)

        workflow = await self._get_owned_workflow(workflow_id=workflow_id, user_id=user.id)
        if workflow is None:
            raise ValueError("Workflow not found")
        self._ensure_workflow_is_active(workflow)
        if require_published and not workflow.is_published:
            raise ValueError("Workflow is not published")

        start_node_id = self._resolve_start_node_id(
            definition=workflow.definition,
            expected_types={"schedule_trigger"},
            preferred_node_id=start_node_id,
        )

        payload = dict(schedule_payload or {})
        payload.setdefault(
            "scheduled_at",
            datetime.now(timezone.utc).astimezone(APP_TIMEZONE).isoformat(),
        )
        payload.setdefault("source", "schedule")
        enqueue_at_utc: datetime | None = None

        if respect_schedule:
            schedule_node = next(
                (
                    node
                    for node in workflow.definition.get("nodes", [])
                    if node.get("id") == start_node_id and node.get("type") == "schedule_trigger"
                ),
                None,
            )
            schedule_config = (
                schedule_node.get("config")
                if isinstance(schedule_node, dict) and isinstance(schedule_node.get("config"), dict)
                else {}
            )
            if not is_schedule_enabled(schedule_config):
                raise ValueError("Selected schedule trigger is disabled")

            next_run_at = next_schedule_run_at(schedule_config)
            if next_run_at is None:
                raise ValueError(
                    "Could not compute next run time for selected schedule trigger"
                )

            enqueue_at_utc = next_run_at
            payload.setdefault("scheduled_for", next_run_at.isoformat())

        return await self._create_and_enqueue_execution(
            workflow=workflow,
            user=user,
            triggered_by="schedule",
            initial_payload=payload,
            start_node_id=start_node_id,
            enqueue_at_utc=enqueue_at_utc,
            loop_control_override=loop_control_override,
        )

    async def create_webhook_execution_by_token(
        self,
        *,
        path_token: str,
        payload: dict[str, Any],
        request_method: str,
    ) -> Execution:
        webhook = await self.db.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.path_token == path_token,
                WebhookEndpoint.is_active.is_(True),
            )
        )
        if webhook is None:
            raise ValueError("Webhook not found")

        workflow = await self.db.scalar(
            select(Workflow).where(
                Workflow.id == webhook.workflow_id,
                Workflow.user_id == webhook.user_id,
            )
        )
        if workflow is None or not workflow.is_published:
            raise ValueError("Webhook not found or workflow not published")
        self._ensure_workflow_is_active(workflow)

        if webhook.node_id == PUBLISHED_RUN_NODE_ID:
            incoming_method = (request_method or "POST").upper()
            allowed_methods = {"GET", "POST"}
            if incoming_method not in allowed_methods:
                allowed = ", ".join(sorted(allowed_methods))
                raise ValueError(
                    f"Webhook method not allowed. Allowed methods: {allowed}. Received {incoming_method}"
                )

            user = await self.db.get(User, workflow.user_id)
            if user is None:
                raise ValueError("Webhook owner not found")

            await self._mark_stale_running_executions(user_id=user.id)

            start_node_id = self._resolve_start_node_id(
                definition=workflow.definition,
            )
            execution_payload = dict(payload or {})
            execution_payload.setdefault("source", "published_url")
            return await self._create_and_enqueue_execution(
                workflow=workflow,
                user=user,
                triggered_by="webhook",
                initial_payload=execution_payload,
                start_node_id=start_node_id,
            )

        node = next(
            (
                item
                for item in workflow.definition.get("nodes", [])
                if item.get("id") == webhook.node_id and item.get("type") == "webhook_trigger"
            ),
            None,
        )
        if node is None:
            raise ValueError("Webhook trigger node not found in workflow")

        expected_method = self._normalize_webhook_method(node.get("config", {}))
        incoming_method = (request_method or "POST").upper()
        if incoming_method != expected_method:
            raise ValueError(
                f"Webhook method not allowed. Expected {expected_method}, received {incoming_method}"
            )

        user = await self.db.get(User, workflow.user_id)
        if user is None:
            raise ValueError("Webhook owner not found")

        await self._mark_stale_running_executions(user_id=user.id)

        return await self._create_and_enqueue_execution(
            workflow=workflow,
            user=user,
            triggered_by="webhook",
            initial_payload=payload,
            start_node_id=webhook.node_id,
        )

    async def get_public_form_definition(
        self,
        *,
        path_token: str,
        base_url: str,
    ) -> dict[str, Any]:
        webhook = await self.db.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.path_token == path_token,
                WebhookEndpoint.is_active.is_(True),
                WebhookEndpoint.node_id == PUBLISHED_RUN_NODE_ID,
            )
        )
        if webhook is None:
            raise ValueError("Public form not found")

        workflow = await self.db.scalar(
            select(Workflow).where(
                Workflow.id == webhook.workflow_id,
                Workflow.user_id == webhook.user_id,
            )
        )
        if workflow is None or not workflow.is_published:
            raise ValueError("Public form not found")
        self._ensure_workflow_is_active(workflow)

        form_node = self._resolve_form_trigger_node(definition=workflow.definition)
        if form_node is None:
            raise ValueError("Public form not found")

        config = form_node.get("config") if isinstance(form_node.get("config"), dict) else {}
        fields = self._sanitize_public_form_fields(config.get("fields"))
        if not fields:
            raise ValueError("Public form has no configured fields")

        stripped_base = base_url.rstrip("/")
        return {
            "workflow_id": workflow.id,
            "workflow_name": str(workflow.name or "Workflow Form"),
            "path_token": path_token,
            "submit_url": f"{stripped_base}/public/forms/{path_token}/submit",
            "form_node_id": str(form_node.get("id") or ""),
            "form_title": str(config.get("form_title") or workflow.name or "Workflow Form"),
            "form_description": str(config.get("form_description") or ""),
            "fields": fields,
        }

    async def create_public_form_execution(
        self,
        *,
        path_token: str,
        form_data: dict[str, Any],
    ) -> Execution:
        webhook = await self.db.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.path_token == path_token,
                WebhookEndpoint.is_active.is_(True),
                WebhookEndpoint.node_id == PUBLISHED_RUN_NODE_ID,
            )
        )
        if webhook is None:
            raise ValueError("Public form not found")

        workflow = await self.db.scalar(
            select(Workflow).where(
                Workflow.id == webhook.workflow_id,
                Workflow.user_id == webhook.user_id,
            )
        )
        if workflow is None or not workflow.is_published:
            raise ValueError("Public form not found")

        user = await self.db.get(User, workflow.user_id)
        if user is None:
            raise ValueError("Public form not found")

        start_node_id = self._resolve_start_node_id(
            definition=workflow.definition,
            expected_types={"form_trigger"},
        )

        await self._mark_stale_running_executions(user_id=user.id)

        payload = dict(form_data or {})
        payload.setdefault("source", "public_form")

        return await self._create_and_enqueue_execution(
            workflow=workflow,
            user=user,
            triggered_by="form",
            initial_payload=payload,
            start_node_id=start_node_id,
        )

    async def create_webhook_execution(
        self,
        *,
        workflow_id: UUID,
        path: str,
        payload: dict[str, Any],
        request_method: str,
    ) -> Execution:
        workflow = await self.db.scalar(select(Workflow).where(Workflow.id == workflow_id))

        if workflow is None or not workflow.is_published:
            raise ValueError("Webhook not found or workflow not published")
        self._ensure_workflow_is_active(workflow)

        incoming_method = (request_method or "POST").upper()
        normalized_path = path.lstrip("/")
        target_node_id = None
        allowed_methods_for_path: set[str] = set()
        for node in workflow.definition.get("nodes", []):
            if node.get("type") == "webhook_trigger":
                config = node.get("config", {}) if isinstance(node.get("config"), dict) else {}
                node_path = str(config.get("path") or "").lstrip("/")
                node_method = self._normalize_webhook_method(config)
                if node_path != normalized_path:
                    continue
                allowed_methods_for_path.add(node_method)
                if node_method == incoming_method:
                    target_node_id = node.get("id")
                    break

        if not target_node_id:
            if allowed_methods_for_path:
                allowed = ", ".join(sorted(allowed_methods_for_path))
                raise ValueError(
                    f"Webhook method not allowed. Allowed methods for this path: {allowed}. Received {incoming_method}"
                )
            raise ValueError("Webhook path not found in workflow")

        user = await self.db.get(User, workflow.user_id)
        if user is None:
            raise ValueError("Webhook owner not found")

        await self._mark_stale_running_executions(user_id=user.id)

        return await self._create_and_enqueue_execution(
            workflow=workflow,
            user=user,
            triggered_by="webhook",
            initial_payload=payload,
            start_node_id=target_node_id,
        )

    async def create_node_test_execution(
        self,
        *,
        workflow_id: UUID,
        node_id: str,
        user: User,
        input_data: dict[str, Any] | None = None,
    ) -> Execution:
        await self._mark_stale_running_executions(user_id=user.id)

        workflow = await self._get_owned_workflow(workflow_id=workflow_id, user_id=user.id)
        if workflow is None:
            raise ValueError("Workflow not found")
        self._ensure_workflow_is_active(workflow)

        # Find the node to get its type for 'triggered_by'
        node = next((n for n in workflow.definition.get("nodes", []) if n["id"] == node_id), None)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found in workflow")

        node_type = node.get("type", "unknown")

        execution = Execution(
            workflow_id=workflow.id,
            user_id=user.id,
            status="PENDING",
            triggered_by=node_type,  # User requested node name/type as trigger type
            started_at=None,
            finished_at=None,
            error_message=None,
        )
        self.db.add(execution)
        await self.db.flush()

        # Create only the target node execution row
        self.db.add(
            NodeExecution(
                execution_id=execution.id,
                node_id=node_id,
                node_type=node_type,
                status="PENDING",
                input_data=input_data,
                output_data=None,
                error_message=None,
                started_at=None,
                finished_at=None,
            )
        )

        await self.db.commit()
        await self.db.refresh(execution)

        try:
            self._enqueue_task(
                run_node_test,
                queue=WORKFLOW_NODE_TEST_QUEUE,
                kwargs={
                    "execution_id": str(execution.id),
                    "node_id": node_id,
                    "input_data": input_data,
                },
            )
        except Exception as exc:
            await self._mark_enqueue_failure(execution=execution, exc=exc)
            raise RuntimeError("Failed to enqueue node test execution") from exc
        return execution

    async def get_execution_detail(
        self,
        *,
        execution_id: UUID,
        user_id: UUID,
    ) -> tuple[Execution, list[NodeExecution]]:
        await self._mark_stale_running_executions(user_id=user_id)

        execution = await self.db.scalar(
            select(Execution)
            .options(
                selectinload(Execution.workflow),
                selectinload(Execution.node_executions),
            )
            .where(Execution.id == execution_id, Execution.user_id == user_id)
        )
        if execution is None:
            raise ValueError("Execution not found")

        workflow = execution.workflow
        node_by_id = {node_execution.node_id: node_execution for node_execution in execution.node_executions}

        executed_rows = sorted(
            [node_execution for node_execution in execution.node_executions if node_execution.status != "PENDING"],
            key=lambda row: row.finished_at or row.started_at or datetime.max,
        )
        executed_ids = {row.node_id for row in executed_rows}

        ordered_nodes: list[NodeExecution] = []
        ordered_nodes.extend(executed_rows)

        for node in workflow.definition.get("nodes", []):
            if node["id"] in executed_ids:
                continue

            existing = node_by_id.get(node["id"])
            if existing is not None:
                ordered_nodes.append(existing)
                continue

            ordered_nodes.append(
                NodeExecution(
                    execution_id=execution.id,
                    node_id=node["id"],
                    node_type=node["type"],
                    status="PENDING",
                    input_data=None,
                    output_data=None,
                    error_message=None,
                    started_at=None,
                    finished_at=None,
                )
            )

        return execution, ordered_nodes

    async def get_latest_execution_detail(
        self,
        *,
        workflow_id: UUID,
        user_id: UUID,
    ) -> tuple[Execution, list[NodeExecution]] | None:
        await self._mark_stale_running_executions(user_id=user_id)

        execution = await self.db.scalar(
            select(Execution)
            .where(
                Execution.workflow_id == workflow_id,
                Execution.user_id == user_id
            )
            .order_by(Execution.started_at.desc().nullslast(), Execution.id.desc())
        )
        if execution is None:
            return None

        return await self.get_execution_detail(
            execution_id=execution.id,
            user_id=user_id
        )

    async def list_executions(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        workflow_id: UUID | None = None,
        status: ExecutionStatus | None = None,
    ) -> tuple[int, Sequence[tuple[Execution, str]]]:
        await self._mark_stale_running_executions(user_id=user_id)

        filters = [Execution.user_id == user_id]
        if workflow_id is not None:
            filters.append(Execution.workflow_id == workflow_id)
        if status is not None:
            filters.append(Execution.status == status)

        total = await self.db.scalar(
            select(func.count())
            .select_from(Execution)
            .where(*filters)
        )

        result = await self.db.execute(
            select(Execution, Workflow.name)
            .join(Workflow, Workflow.id == Execution.workflow_id)
            .where(*filters)
            .order_by(Execution.started_at.desc().nullslast(), Execution.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return int(total or 0), result.all()

    async def stop_execution(
        self,
        *,
        execution_id: UUID,
        user_id: UUID,
    ) -> tuple[Execution, list[NodeExecution]]:
        execution = await self.db.scalar(
            select(Execution).where(
                Execution.id == execution_id,
                Execution.user_id == user_id,
            )
        )
        if execution is None:
            raise ValueError("Execution not found")

        if execution.status in {"PENDING", "QUEUED", "WAITING", "RUNNING"}:
            now = datetime.now(timezone.utc)
            execution.status = "FAILED"
            execution.finished_at = now
            execution.error_message = MANUAL_STOP_ERROR_MESSAGE

            node_rows = (
                await self.db.scalars(
                    select(NodeExecution).where(
                        NodeExecution.execution_id == execution.id,
                        NodeExecution.status.in_(["PENDING", "QUEUED", "WAITING", "RUNNING"]),
                    )
                )
            ).all()
            for node_row in node_rows:
                node_row.status = "FAILED"
                node_row.error_message = MANUAL_STOP_ERROR_MESSAGE
                node_row.started_at = node_row.started_at or now
                node_row.finished_at = now

            await self.db.commit()

        return await self.get_execution_detail(
            execution_id=execution.id,
            user_id=user_id,
        )

    async def _create_and_enqueue_execution(
        self,
        *,
        workflow: Workflow,
        user: User,
        triggered_by: TriggeredBy,
        initial_payload: dict | None,
        start_node_id: str,
        enqueue_at_utc: datetime | None = None,
        loop_control_override: dict[str, Any] | None = None,
    ) -> Execution:
        execution = Execution(
            workflow_id=workflow.id,
            user_id=user.id,
            status="PENDING",
            triggered_by=triggered_by,
            started_at=None,
            finished_at=None,
            error_message=None,
        )
        self.db.add(execution)
        await self.db.flush()

        for node in workflow.definition.get("nodes", []):
            self.db.add(
                NodeExecution(
                    execution_id=execution.id,
                    node_id=node["id"],
                    node_type=node["type"],
                    status="PENDING",
                    input_data=None,
                    output_data=None,
                    error_message=None,
                    started_at=None,
                    finished_at=None,
                )
            )

        await self.db.commit()
        await self.db.refresh(execution)

        try:
            self._enqueue_task(
                run_execution,
                queue=WORKFLOW_EXECUTION_QUEUE,
                eta=enqueue_at_utc,
                kwargs={
                    "execution_id": str(execution.id),
                    "initial_payload": initial_payload,
                    "start_node_id": start_node_id,
                    "loop_control_override": self._sanitize_loop_control_override(
                        loop_control_override
                    ),
                },
            )
        except Exception as exc:
            await self._mark_enqueue_failure(execution=execution, exc=exc)
            raise RuntimeError("Failed to enqueue workflow execution") from exc
        return execution

    async def _get_owned_workflow(self, *, workflow_id: UUID, user_id: UUID) -> Workflow | None:
        workflow = await self.db.scalar(
            select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == user_id)
        )
        return workflow

    @staticmethod
    def _resolve_start_node_id(
        *,
        definition: dict,
        expected_types: set[str] | str = None,
        preferred_node_id: str | None = None,
    ) -> str:
        if isinstance(expected_types, str):
            expected_types = {expected_types}
            
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])
        node_by_id = {node.get("id"): node for node in nodes}
        indegree = {node.get("id"): 0 for node in nodes}
        for edge in edges:
            target = edge.get("target")
            if target in indegree:
                indegree[target] += 1

        default_trigger_types = {"manual_trigger", "form_trigger", "schedule_trigger", "webhook_trigger", "workflow_trigger"}
        allowed_types = expected_types or default_trigger_types

        if preferred_node_id:
            preferred_node = node_by_id.get(preferred_node_id)
            if preferred_node is None:
                raise ValueError(
                    f"Selected start node '{preferred_node_id}' was not found in workflow"
                )

            preferred_type = preferred_node.get("type")
            if preferred_type not in allowed_types:
                allowed_types_label = ", ".join(sorted(allowed_types))
                raise ValueError(
                    f"Selected start node '{preferred_node_id}' must be one of: {allowed_types_label}"
                )

            if indegree.get(preferred_node_id, 0) != 0:
                raise ValueError(
                    f"Selected start node '{preferred_node_id}' must be a root trigger with no incoming edges"
                )
            return preferred_node_id

        candidates = [
            node
            for node in nodes
            if indegree.get(node.get("id")) == 0
        ]
        
        candidates = [c for c in candidates if c.get("type") in allowed_types]

        if not candidates:
            raise ValueError(f"Workflow does not have a valid start node")
            
        # Prioritize manual_trigger if multiple triggers are found
        manual_triggers = [c for c in candidates if c.get("type") == "manual_trigger"]
        if manual_triggers:
            return manual_triggers[0]["id"]

        # Otherwise just return the first valid trigger found (allows testing form/webhook flows)
        return candidates[0]["id"]

    @staticmethod
    def _normalize_webhook_method(config: dict[str, Any] | None) -> str:
        if not isinstance(config, dict):
            return "POST"
        return str(config.get("method") or "POST").upper()

    @staticmethod
    def _resolve_form_trigger_node(*, definition: dict[str, Any]) -> dict[str, Any] | None:
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
    def _sanitize_public_form_fields(raw_fields: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_fields, list):
            return []

        fields: list[dict[str, Any]] = []
        for index, raw_field in enumerate(raw_fields):
            if not isinstance(raw_field, dict):
                continue
            name = str(raw_field.get("name") or f"field_{index + 1}").strip()
            if not name:
                continue
            label = str(raw_field.get("label") or name).strip() or name
            field_type = str(raw_field.get("type") or "text").strip().lower() or "text"
            if field_type not in {
                "text",
                "email",
                "number",
                "password",
                "url",
                "tel",
                "date",
                "datetime-local",
                "textarea",
            }:
                field_type = "text"

            fields.append(
                {
                    "name": name,
                    "label": label,
                    "type": field_type,
                    "required": bool(raw_field.get("required")),
                }
            )
        return fields

    @staticmethod
    def _enqueue_task(
        task,
        *,
        queue: str,
        kwargs: dict[str, Any],
        eta: datetime | None = None,
    ) -> None:
        inspector = task.app.control.inspect(timeout=1.0)
        active_queues = inspector.active_queues() if inspector is not None else None
        target_queue = queue
        if isinstance(active_queues, dict) and active_queues:
            queue_consumers = [
                worker_name
                for worker_name, queues in active_queues.items()
                if any((q or {}).get("name") == queue for q in (queues or []))
            ]
            if not queue_consumers:
                legacy_consumers = [
                    worker_name
                    for worker_name, queues in active_queues.items()
                    if any((q or {}).get("name") == "celery" for q in (queues or []))
                ]
                if legacy_consumers:
                    # Backward-compatible fallback for deployments still running
                    # workers on the default Celery queue.
                    target_queue = "celery"
                else:
                    raise RuntimeError(
                        f"No Celery worker is consuming queue '{queue}'. "
                        f"Start a worker with '-Q {queue}' (or include this queue in worker startup)."
                    )

        apply_async_kwargs: dict[str, Any] = {
            "kwargs": kwargs,
            "queue": target_queue,
            "retry": True,
            "retry_policy": {
                "max_retries": 8,
                "interval_start": 0,
                "interval_step": 1,
                "interval_max": 8,
            },
        }
        if isinstance(eta, datetime):
            apply_async_kwargs["eta"] = eta

        task.apply_async(**apply_async_kwargs)

    async def _mark_enqueue_failure(self, *, execution: Execution, exc: Exception) -> None:
        execution.status = "FAILED"
        execution.finished_at = datetime.now(timezone.utc)
        execution.error_message = to_user_friendly_error_message(
            exc,
            fallback=(
                "Could not start background execution. Please ensure workers are running and retry."
            ),
        )
        await self.db.commit()

    async def _mark_stale_running_executions(self, *, user_id: UUID) -> None:
        timeout_minutes = self._stale_running_timeout_minutes()
        if timeout_minutes <= 0:
            return

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=timeout_minutes)
        stale_rows = (
            await self.db.scalars(
                select(Execution).where(
                    Execution.user_id == user_id,
                    Execution.status == "RUNNING",
                    Execution.started_at.is_not(None),
                    Execution.started_at < cutoff,
                )
            )
        ).all()
        if not stale_rows:
            return

        stale_execution_ids = [row.id for row in stale_rows]
        failure_message = (
            "Execution timed out or worker was interrupted. "
            "Marked as failed by stale-execution recovery."
        )

        active_node_rows = (
            await self.db.scalars(
                select(NodeExecution).where(
                    NodeExecution.execution_id.in_(stale_execution_ids),
                    NodeExecution.status.in_(["PENDING", "QUEUED", "WAITING", "RUNNING"]),
                )
            )
        ).all()

        node_rows_by_execution: dict[UUID, list[NodeExecution]] = {}
        for node_row in active_node_rows:
            node_rows_by_execution.setdefault(node_row.execution_id, []).append(node_row)

        recoverable_ids: set[UUID] = set()
        failed_ids: set[UUID] = set()

        for execution in stale_rows:
            rows = node_rows_by_execution.get(execution.id, [])
            status_set = {str(row.status or "").upper() for row in rows}
            has_waiting_or_queued = bool(status_set.intersection({"QUEUED", "WAITING"}))

            if has_waiting_or_queued:
                execution.status = "WAITING"
                execution.finished_at = None
                if execution.error_message == failure_message:
                    execution.error_message = None
                recoverable_ids.add(execution.id)
            else:
                execution.status = "FAILED"
                execution.finished_at = now
                if not execution.error_message:
                    execution.error_message = failure_message
                failed_ids.add(execution.id)

        for node_row in active_node_rows:
            if node_row.execution_id in recoverable_ids:
                if node_row.status in {"PENDING", "RUNNING"}:
                    node_row.status = "QUEUED"
                    node_row.finished_at = None
                    if node_row.error_message == failure_message:
                        node_row.error_message = None
                continue

            if node_row.execution_id in failed_ids and node_row.status in {"PENDING", "RUNNING"}:
                node_row.status = "FAILED"
                node_row.finished_at = now
                if not node_row.error_message:
                    node_row.error_message = failure_message

        await self.db.commit()

    @staticmethod
    def _stale_running_timeout_minutes() -> int:
        raw_value = os.getenv("EXECUTION_STALE_TIMEOUT_MINUTES", "30")
        try:
            return max(0, int(raw_value))
        except Exception:
            return 30

    @staticmethod
    def _sanitize_loop_control_override(
        loop_control_override: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(loop_control_override, dict):
            return None

        result: dict[str, Any] = {}
        if loop_control_override.get("enabled") is not None:
            raw_enabled = loop_control_override.get("enabled")
            if isinstance(raw_enabled, bool):
                result["enabled"] = raw_enabled
            elif isinstance(raw_enabled, (int, float)):
                result["enabled"] = bool(raw_enabled)
            elif isinstance(raw_enabled, str):
                normalized = raw_enabled.strip().lower()
                if normalized in {"true", "1", "yes", "on"}:
                    result["enabled"] = True
                elif normalized in {"false", "0", "no", "off"}:
                    result["enabled"] = False

        if loop_control_override.get("max_node_executions") is not None:
            try:
                result["max_node_executions"] = max(
                    1, int(loop_control_override["max_node_executions"])
                )
            except Exception:
                pass
        if loop_control_override.get("max_total_node_executions") is not None:
            try:
                result["max_total_node_executions"] = max(
                    1, int(loop_control_override["max_total_node_executions"])
                )
            except Exception:
                pass

        return result or None
