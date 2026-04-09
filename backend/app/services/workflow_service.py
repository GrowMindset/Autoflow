from __future__ import annotations

from secrets import token_urlsafe
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
        workflow = Workflow(
            user_id=user_id,
            name=payload.name,
            description=payload.description,
            definition=payload.definition.model_dump(mode="python"),
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
            updates["definition"] = payload.definition.model_dump(mode="python")

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

    async def _ensure_webhook_endpoints(self, workflow: Workflow) -> None:
        trigger_node_ids = [
            node["id"]
            for node in workflow.definition.get("nodes", [])
            if node.get("type") == "webhook_trigger"
        ]
        if not trigger_node_ids:
            return

        existing = (
            await self.db.scalars(
                select(WebhookEndpoint).where(WebhookEndpoint.workflow_id == workflow.id)
            )
        ).all()
        existing_by_node_id = {webhook.node_id: webhook for webhook in existing}

        for node_id in trigger_node_ids:
            if node_id in existing_by_node_id:
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

        await self.db.commit()
