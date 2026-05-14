from __future__ import annotations

from uuid import UUID
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.workflows import (
    WorkflowCreate,
    WorkflowDeleteResponse,
    WorkflowListItem,
    WorkflowListResponse,
    WorkflowVersionCreate,
    WorkflowVersionListItem,
    WorkflowVersionListResponse,
    WorkflowVersionResponse,
    WorkflowWebhookEndpoint,
    WorkflowWebhookListResponse,
    WorkflowResponse,
    WorkflowUpdate,
)
from app.services.workflow_service import (
    InactiveWorkflowPublishError,
    PublishedWorkflowEditError,
    WorkflowService,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _resolve_frontend_base_from_request(request: Request) -> str | None:
    origin = str(request.headers.get("origin") or "").strip()
    if origin.startswith("http://") or origin.startswith("https://"):
        return origin.rstrip("/")

    referer = str(request.headers.get("referer") or "").strip()
    if not referer:
        return None
    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


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
    try:
        workflow = await workflow_service.update_workflow(
            workflow_id=workflow_id,
            user_id=current_user.id,
            payload=payload,
        )
    except PublishedWorkflowEditError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowResponse.model_validate(workflow)


@router.post("/{workflow_id}/publish", response_model=WorkflowResponse)
async def publish_workflow(
    workflow_id: UUID,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    try:
        workflow = await workflow_service.publish_workflow(
            workflow_id=workflow_id,
            user_id=current_user.id,
        )
    except InactiveWorkflowPublishError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowResponse.model_validate(workflow)


@router.post("/{workflow_id}/unpublish", response_model=WorkflowResponse)
async def unpublish_workflow(
    workflow_id: UUID,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    workflow = await workflow_service.unpublish_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
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


@router.post(
    "/{workflow_id}/versions",
    response_model=WorkflowVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_version(
    workflow_id: UUID,
    payload: WorkflowVersionCreate | None = None,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowVersionResponse:
    version = await workflow_service.create_workflow_version(
        workflow_id=workflow_id,
        user_id=current_user.id,
        note=payload.note if payload else None,
    )
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowVersionResponse.model_validate(version)


@router.get("/{workflow_id}/versions", response_model=WorkflowVersionListResponse)
async def list_workflow_versions(
    workflow_id: UUID,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowVersionListResponse:
    versions = await workflow_service.list_workflow_versions(
        workflow_id=workflow_id,
        user_id=current_user.id,
    )
    if versions is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowVersionListResponse(
        versions=[WorkflowVersionListItem.model_validate(version) for version in versions]
    )


@router.get("/{workflow_id}/versions/{version_id}", response_model=WorkflowVersionResponse)
async def get_workflow_version(
    workflow_id: UUID,
    version_id: UUID,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowVersionResponse:
    workflow = await workflow_service.get_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    version = await workflow_service.get_workflow_version(
        workflow_id=workflow_id,
        version_id=version_id,
        user_id=current_user.id,
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow version not found",
        )
    return WorkflowVersionResponse.model_validate(version)


@router.post("/{workflow_id}/restore/{version_id}", response_model=WorkflowResponse)
async def restore_workflow_version(
    workflow_id: UUID,
    version_id: UUID,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResponse:
    workflow = await workflow_service.get_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    version = await workflow_service.get_workflow_version(
        workflow_id=workflow_id,
        version_id=version_id,
        user_id=current_user.id,
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow version not found",
        )

    try:
        restored = await workflow_service.restore_workflow_version(
            workflow_id=workflow_id,
            version_id=version_id,
            user_id=current_user.id,
        )
    except PublishedWorkflowEditError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if restored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowResponse.model_validate(restored)


@router.get("/{workflow_id}/webhooks", response_model=WorkflowWebhookListResponse)
async def list_workflow_webhooks(
    workflow_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowWebhookListResponse:
    workflow = await workflow_service.get_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    webhooks = await workflow_service.get_webhook_endpoints(
        workflow_id=workflow_id,
        user_id=current_user.id,
        base_url=str(request.base_url),
    )
    return WorkflowWebhookListResponse(
        webhooks=[WorkflowWebhookEndpoint(**item) for item in webhooks]
    )


@router.get("/{workflow_id}/public-run-url", response_model=WorkflowWebhookEndpoint)
async def get_public_run_url(
    workflow_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowWebhookEndpoint:
    workflow = await workflow_service.get_workflow(
        workflow_id=workflow_id,
        user_id=current_user.id,
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    endpoint = await workflow_service.get_public_run_endpoint(
        workflow_id=workflow_id,
        user_id=current_user.id,
        base_url=str(request.base_url),
        frontend_base_url=_resolve_frontend_base_from_request(request),
    )
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No trigger found for public run URL",
        )
    return WorkflowWebhookEndpoint(**endpoint)
