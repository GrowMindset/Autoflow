from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.workflows import (
    WorkflowCreate,
    WorkflowDeleteResponse,
    WorkflowListItem,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowUpdate,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


def get_workflow_service(db: AsyncSession = Depends(get_db)) -> WorkflowService:
    return WorkflowService(db)


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    workflow = await workflow_service.create_workflow(user_id=current_user.id, payload=payload)
    return WorkflowResponse.model_validate(workflow)


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowListResponse:
    total, workflows = await workflow_service.list_workflows(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return WorkflowListResponse(
        total=total,
        limit=limit,
        offset=offset,
        next_cursor=None,
        workflows=[WorkflowListItem.model_validate(workflow) for workflow in workflows],
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: UUID,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    workflow = await workflow_service.get_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowResponse.model_validate(workflow)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    workflow = await workflow_service.update_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
        payload=payload,
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowResponse.model_validate(workflow)


@router.delete("/{workflow_id}", response_model=WorkflowDeleteResponse)
async def delete_workflow(
    workflow_id: UUID,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowDeleteResponse:
    deleted = await workflow_service.delete_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowDeleteResponse(message="Workflow deleted successfully")
