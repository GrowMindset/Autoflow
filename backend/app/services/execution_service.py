from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.executions import Execution
from app.models.nodes_executions import NodeExecution
from app.models.user import User
from app.models.webhook import WebhookEndpoint
from app.models.workflows import Workflow
from app.schemas.executions import ExecutionStatus, TriggeredBy
from app.tasks.execute_workflow import run_execution, run_node_test


class ExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_manual_execution(
        self,
        *,
        workflow_id: UUID,
        user: User,
    ) -> Execution:
        workflow = await self._get_owned_workflow(workflow_id=workflow_id, user_id=user.id)
        if workflow is None:
            raise ValueError("Workflow not found")

        start_node_id = self._resolve_start_node_id(
            definition=workflow.definition,
            expected_type="manual_trigger",
        )
        return await self._create_and_enqueue_execution(
            workflow=workflow,
            user=user,
            triggered_by="manual",
            initial_payload=None,
            start_node_id=start_node_id,
        )

    async def create_form_execution(
        self,
        *,
        workflow_id: UUID,
        user: User,
        form_data: dict[str, str],
    ) -> Execution:
        workflow = await self._get_owned_workflow(workflow_id=workflow_id, user_id=user.id)
        if workflow is None:
            raise ValueError("Workflow not found")

        start_node_id = self._resolve_start_node_id(
            definition=workflow.definition,
            expected_type="form_trigger",
        )
        return await self._create_and_enqueue_execution(
            workflow=workflow,
            user=user,
            triggered_by="form",
            initial_payload=form_data,
            start_node_id=start_node_id,
        )

    async def create_webhook_execution(
        self,
        *,
        path_token: str,
        payload: dict,
    ) -> Execution:
        webhook = await self.db.scalar(
            select(WebhookEndpoint)
            .options(selectinload(WebhookEndpoint.workflow))
            .where(
                WebhookEndpoint.path_token == path_token,
                WebhookEndpoint.is_active.is_(True),
            )
        )
        if webhook is None:
            raise ValueError("Webhook not found")

        workflow = webhook.workflow
        if workflow is None or not workflow.is_published:
            raise ValueError("Webhook not found")

        user = await self.db.get(User, webhook.user_id)
        if user is None:
            raise ValueError("Webhook not found")

        return await self._create_and_enqueue_execution(
            workflow=workflow,
            user=user,
            triggered_by="webhook",
            initial_payload=payload,
            start_node_id=webhook.node_id,
        )

    async def create_node_test_execution(
        self,
        *,
        workflow_id: UUID,
        node_id: str,
        user: User,
        input_data: dict[str, Any] | None = None,
    ) -> Execution:
        workflow = await self._get_owned_workflow(workflow_id=workflow_id, user_id=user.id)
        if workflow is None:
            raise ValueError("Workflow not found")

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

        run_node_test.delay(
            execution_id=str(execution.id),
            node_id=node_id,
            input_data=input_data,
        )
        return execution

    async def get_execution_detail(
        self,
        *,
        execution_id: UUID,
        user_id: UUID,
    ) -> tuple[Execution, list[NodeExecution]]:
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
        ordered_nodes: list[NodeExecution] = []

        for node in workflow.definition.get("nodes", []):
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

    async def list_executions(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
        workflow_id: UUID | None = None,
        status: ExecutionStatus | None = None,
    ) -> tuple[int, Sequence[tuple[Execution, str]]]:
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

    async def _create_and_enqueue_execution(
        self,
        *,
        workflow: Workflow,
        user: User,
        triggered_by: TriggeredBy,
        initial_payload: dict | None,
        start_node_id: str,
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

        run_execution.delay(
            execution_id=str(execution.id),
            initial_payload=initial_payload,
            start_node_id=start_node_id,
        )
        return execution

    async def _get_owned_workflow(self, *, workflow_id: UUID, user_id: UUID) -> Workflow | None:
        workflow = await self.db.scalar(
            select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == user_id)
        )
        return workflow

    @staticmethod
    def _resolve_start_node_id(*, definition: dict, expected_type: str) -> str:
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])
        indegree = {node.get("id"): 0 for node in nodes}
        for edge in edges:
            target = edge.get("target")
            if target in indegree:
                indegree[target] += 1

        candidates = [
            node["id"]
            for node in nodes
            if node.get("type") == expected_type and indegree.get(node.get("id")) == 0
        ]
        if not candidates:
            raise ValueError(f"Workflow does not have a valid {expected_type} start node")
        if len(candidates) > 1:
            raise ValueError(f"Workflow has multiple {expected_type} start nodes")
        return candidates[0]
