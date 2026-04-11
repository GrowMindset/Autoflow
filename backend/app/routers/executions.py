from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.executions import (
    ExecutionDetailResponse,
    ExecutionEnqueueResponse,
    ExecutionListItem,
    ExecutionListResponse,
    ExecutionStatus,
    NodeExecutionResult,
    RunFormRequest,
    RunNodeTestRequest,
    WebhookEnqueueResponse,
)
from app.services.execution_service import ExecutionService

router = APIRouter(tags=["executions"])


def get_execution_service(db: AsyncSession = Depends(get_db)) -> ExecutionService:
    return ExecutionService(db)


@router.post(
    "/workflows/{workflow_id}/run",
    response_model=ExecutionEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_workflow(
    workflow_id: UUID,
    current_user: User = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionEnqueueResponse:
    try:
        execution = await execution_service.create_manual_execution(
            workflow_id=workflow_id,
            user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ExecutionEnqueueResponse(
        execution_id=execution.id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        triggered_by=execution.triggered_by,
    )


@router.post(
    "/workflows/{workflow_id}/run-form",
    response_model=ExecutionEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_workflow_form(
    workflow_id: UUID,
    payload: RunFormRequest,
    current_user: User = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionEnqueueResponse:
    try:
        execution = await execution_service.create_form_execution(
            workflow_id=workflow_id,
            user=current_user,
            form_data=payload.form_data,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if detail == "Workflow not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc

    return ExecutionEnqueueResponse(
        execution_id=execution.id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        triggered_by=execution.triggered_by,
    )


@router.post(
    "/workflows/{workflow_id}/nodes/{node_id}/execute",
    response_model=ExecutionEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_node_execute(
    workflow_id: UUID,
    node_id: str,
    payload: RunNodeTestRequest,
    current_user: User = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionEnqueueResponse:
    try:
        execution = await execution_service.create_node_test_execution(
            workflow_id=workflow_id,
            node_id=node_id,
            user=current_user,
            input_data=payload.input_data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ExecutionEnqueueResponse(
        execution_id=execution.id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        triggered_by=execution.triggered_by,
    )


@router.get("/executions/{execution_id}", response_model=ExecutionDetailResponse)
async def get_execution(
    execution_id: UUID,
    current_user: User = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionDetailResponse:
    try:
        execution, node_results = await execution_service.get_execution_detail(
            execution_id=execution_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ExecutionDetailResponse(
        id=execution.id,
        workflow_id=execution.workflow_id,
        user_id=execution.user_id,
        status=execution.status,
        triggered_by=execution.triggered_by,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        error_message=execution.error_message,
        node_results=[
            NodeExecutionResult(
                node_id=node.node_id,
                node_type=node.node_type,
                status=node.status,
                input_data=node.input_data,
                output_data=node.output_data,
                error_message=node.error_message,
                started_at=node.started_at,
                finished_at=node.finished_at,
            )
            for node in node_results
        ],
    )


@router.get("/workflows/{workflow_id}/executions/latest", response_model=ExecutionDetailResponse)
async def get_latest_execution(
    workflow_id: UUID,
    current_user: User = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionDetailResponse:
    result = await execution_service.get_latest_execution_detail(
        workflow_id=workflow_id,
        user_id=current_user.id,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No executions found")

    execution, node_results = result
    return ExecutionDetailResponse(
        id=execution.id,
        workflow_id=execution.workflow_id,
        user_id=execution.user_id,
        status=execution.status,
        triggered_by=execution.triggered_by,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        error_message=execution.error_message,
        node_results=[
            NodeExecutionResult(
                node_id=node.node_id,
                node_type=node.node_type,
                status=node.status,
                input_data=node.input_data,
                output_data=node.output_data,
                error_message=node.error_message,
                started_at=node.started_at,
                finished_at=node.finished_at,
            )
            for node in node_results
        ],
    )


@router.get("/executions", response_model=ExecutionListResponse)
async def list_executions(
    limit: int = Query(default=20, ge=1),
    offset: int = Query(default=0, ge=0),
    workflow_id: UUID | None = Query(default=None),
    status_filter: ExecutionStatus | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ExecutionListResponse:
    total, executions = await execution_service.list_executions(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        workflow_id=workflow_id,
        status=status_filter,
    )
    return ExecutionListResponse(
        total=total,
        limit=limit,
        offset=offset,
        executions=[
            ExecutionListItem(
                id=execution.id,
                workflow_id=execution.workflow_id,
                workflow_name=workflow_name,
                status=execution.status,
                triggered_by=execution.triggered_by,
                started_at=execution.started_at,
                finished_at=execution.finished_at,
                error_message=execution.error_message,
            )
            for execution, workflow_name in executions
        ],
    )


@router.post(
    "/webhook/{path_token}",
    response_model=WebhookEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_webhook(
    path_token: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> WebhookEnqueueResponse:
    try:
        execution = await execution_service.create_webhook_execution(
            path_token=path_token,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return WebhookEnqueueResponse(
        execution_id=execution.id,
        message="Workflow execution enqueued",
    )
