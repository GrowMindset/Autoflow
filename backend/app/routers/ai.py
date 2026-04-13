from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.ai import GenerateWorkflowRequest, GenerateWorkflowResponse
from app.services.llm_service import LLMService, WorkflowGenerationError

router = APIRouter(prefix="/ai", tags=["ai"])


def get_llm_service() -> LLMService:
    return LLMService()


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
        definition = await llm_service.generate_workflow_definition(payload.prompt)
    except WorkflowGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "workflow_generation_failed",
                "message": str(exc),
            },
        ) from exc

    return GenerateWorkflowResponse(definition=definition)
