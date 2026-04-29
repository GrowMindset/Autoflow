from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.ai import (
    AIChatHistoryClearResponse,
    AIChatHistoryResponse,
    AIChatHistoryUpsertRequest,
    GenerateCodeRequest,
    GenerateWorkflowRequest,
    GenerateWorkflowResponse,
    WorkflowAssistantRequest,
    WorkflowAssistantResponse,
)
from app.services.ai_chat_history_service import (
    AIChatHistoryService,
    AIChatHistoryStorageUnavailableError,
)
from app.services.credential_service import CredentialService
from app.services.llm_service import LLMService, WorkflowGenerationError

router = APIRouter(prefix="/ai", tags=["ai"])


def get_llm_service() -> LLMService:
    return LLMService()


def get_ai_chat_history_service(
    db: AsyncSession = Depends(get_db),
) -> AIChatHistoryService:
    return AIChatHistoryService(db)


def get_credential_service(db: AsyncSession = Depends(get_db)) -> CredentialService:
    return CredentialService(db)


@router.post("/generate-code", status_code=status.HTTP_200_OK)
async def generate_code(
    body: GenerateCodeRequest,
    current_user: User = Depends(get_current_user),
    credential_service: CredentialService = Depends(get_credential_service),
) -> dict[str, str]:
    prompt = body.prompt.strip()
    language = body.language
    api_key = str(body.api_key or "").strip()
    input_fields = [
        str(field).strip()
        for field in (body.input_fields or [])
        if str(field).strip()
    ]

    if body.credential_id is not None:
        credential = await credential_service.get_credential(
            current_user.id,
            body.credential_id,
        )
        if credential is None or credential.app_name != "openai":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="OpenAI credential not found.",
            )
        api_key = credential_service.get_decrypted_api_key(credential) or ""

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenAI API key is required.",
        )

    if language == "python":
        syntax_note = 'IMPORTANT: input_data is a Python dict. ALWAYS use input_data["field"] bracket notation. NEVER use input_data.field dot notation.'
        code_example = 'n = int(input_data["number"])\noutput = {"result": n}'
        if input_fields:
            access_example = "\n".join([f'  input_data["{f}"]' for f in input_fields])
        else:
            access_example = '  input_data["your_field"]'
    else:
        syntax_note = "IMPORTANT: input_data is a JavaScript object. ALWAYS use input_data.field dot notation. NEVER use input_data['field'] or input_data[\"field\"]."
        code_example = "const n = parseInt(input_data.number);\nconst output = { result: n };"
        if input_fields:
            access_example = "\n".join([f"  input_data.{f}" for f in input_fields])
        else:
            access_example = "  input_data.your_field"

    fields_hint = ""
    if input_fields:
        fields_hint = f"\nThe input_data object has exactly these fields: {', '.join(input_fields)}\nAccess them like this:\n{access_example}\n"

    system_prompt = f"""
        You are a code generator for a workflow automation tool.
        The user will describe what they want in plain English.
        Generate ONLY a {language} code snippet - no explanation, no markdown, no backticks.

        {syntax_note}

        The code must follow these rules:
        - Input data is available as `input_data`
        {fields_hint}
        - The result must be assigned to a variable called `output` (a dict/object)
        - No external libraries or imports beyond standard library
        - Keep it concise and correct

        Example:
        {code_example}
        """

    try:
        import openai

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.2,
        )
        code = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "code_generation_failed",
                "message": str(exc) or "Failed to generate code.",
            },
        ) from exc

    code = re.sub(r"^```[\w-]*\n?", "", code)
    code = re.sub(r"\n?```$", "", code).strip()

    return {"code": code}


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
