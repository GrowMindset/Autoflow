from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.ai import (
    AIChatHistoryClearResponse,
    AIChatHistoryResponse,
    AIChatHistoryUpsertRequest,
    GenerateWorkflowRequest,
    GenerateWorkflowResponse,
    WorkflowAssistantRequest,
    WorkflowAssistantResponse,
)
from app.services.ai_chat_history_service import (
    AIChatHistoryService,
    AIChatHistoryStorageUnavailableError,
)
from app.services.llm_service import LLMService, WorkflowGenerationError

router = APIRouter(prefix="/ai", tags=["ai"])


def get_llm_service() -> LLMService:
    return LLMService()


def get_ai_chat_history_service(
    db: AsyncSession = Depends(get_db),
) -> AIChatHistoryService:
    return AIChatHistoryService(db)


@router.post(
    "/workflow-assistant",
    response_model=WorkflowAssistantResponse,
    status_code=status.HTTP_200_OK,
)
async def workflow_assistant(
    payload: WorkflowAssistantRequest,
    _: User = Depends(get_current_user),
    llm_service: LLMService = Depends(get_llm_service),
) -> WorkflowAssistantResponse:
    try:
        result = await llm_service.assist_workflow(
            prompt=payload.prompt,
            current_definition=payload.current_definition,
            conversation_state=payload.conversation_state.model_dump(),
        )
        return WorkflowAssistantResponse(**result)
    except WorkflowGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "workflow_generation_failed",
                "message": str(exc),
                "mode": "clarify",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "workflow_generation_upstream_error",
                "message": str(exc) or "Failed to assist workflow from AI provider.",
            },
        ) from exc


@router.get(
    "/chat-history/{scope_key}",
    response_model=AIChatHistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_chat_history(
    scope_key: str,
    current_user: User = Depends(get_current_user),
    history_service: AIChatHistoryService = Depends(get_ai_chat_history_service),
) -> AIChatHistoryResponse:
    try:
        payload = await history_service.get_scope_history(
            user_id=current_user.id,
            scope_key=scope_key,
        )
        return AIChatHistoryResponse(**payload)
    except AIChatHistoryStorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ai_chat_history_unavailable",
                "message": str(exc),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.put(
    "/chat-history/{scope_key}",
    response_model=AIChatHistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def upsert_chat_history(
    scope_key: str,
    payload: AIChatHistoryUpsertRequest,
    current_user: User = Depends(get_current_user),
    history_service: AIChatHistoryService = Depends(get_ai_chat_history_service),
) -> AIChatHistoryResponse:
    try:
        result = await history_service.save_scope_history(
            user_id=current_user.id,
            scope_key=scope_key,
            messages=[item.model_dump(mode="python") for item in payload.messages],
            conversation_state=payload.conversation_state,
        )
        return AIChatHistoryResponse(**result)
    except AIChatHistoryStorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ai_chat_history_unavailable",
                "message": str(exc),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.delete(
    "/chat-history/{scope_key}",
    response_model=AIChatHistoryClearResponse,
    status_code=status.HTTP_200_OK,
)
async def clear_scope_chat_history(
    scope_key: str,
    current_user: User = Depends(get_current_user),
    history_service: AIChatHistoryService = Depends(get_ai_chat_history_service),
) -> AIChatHistoryClearResponse:
    try:
        result = await history_service.clear_scope_history(
            user_id=current_user.id,
            scope_key=scope_key,
        )
        return AIChatHistoryClearResponse(
            message="AI chat history cleared for scope.",
            deleted_messages=result["deleted_messages"],
            deleted_states=result["deleted_states"],
        )
    except AIChatHistoryStorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ai_chat_history_unavailable",
                "message": str(exc),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.delete(
    "/chat-history",
    response_model=AIChatHistoryClearResponse,
    status_code=status.HTTP_200_OK,
)
async def clear_all_chat_history(
    current_user: User = Depends(get_current_user),
    history_service: AIChatHistoryService = Depends(get_ai_chat_history_service),
) -> AIChatHistoryClearResponse:
    try:
        result = await history_service.clear_all_history(user_id=current_user.id)
        return AIChatHistoryClearResponse(
            message="All AI chat history cleared.",
            deleted_messages=result["deleted_messages"],
            deleted_states=result["deleted_states"],
        )
    except AIChatHistoryStorageUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ai_chat_history_unavailable",
                "message": str(exc),
            },
        ) from exc


@router.post(
    "/generate-workflow",
    response_model=GenerateWorkflowResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_workflow(
    payload: GenerateWorkflowRequest,
    _: User = Depends(get_current_user),
    llm_service: LLMService = Depends(get_llm_service),
) -> GenerateWorkflowResponse:
    try:
        generated = await llm_service.generate_workflow_definition(payload.prompt)
    except WorkflowGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "workflow_generation_failed",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "workflow_generation_upstream_error",
                "message": str(exc) or "Failed to generate workflow from AI provider.",
            },
        ) from exc

    return GenerateWorkflowResponse(definition=generated.definition, name=generated.name)
