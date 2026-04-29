from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.workflows import WorkflowDefinition


class GenerateWorkflowRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class GenerateWorkflowResponse(BaseModel):
    definition: WorkflowDefinition
    name: str | None = Field(default=None, min_length=1, max_length=100)


class GenerateCodeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    language: Literal["python", "javascript"]
    api_key: str | None = Field(default=None, max_length=500)
    credential_id: UUID | None = None
    input_fields: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_api_key_or_credential(self) -> "GenerateCodeRequest":
        if self.credential_id is None and not str(self.api_key or "").strip():
            raise ValueError("Provide either api_key or credential_id.")
        return self


class AIErrorDetail(BaseModel):
    code: str
    message: str


AssistantMode = Literal["clarify", "generate", "modify"]


class ClarificationQuestion(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=240)


class ConversationState(BaseModel):
    confirmed_choices: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    last_mode: AssistantMode | None = None


class WorkflowAssistantRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    current_definition: WorkflowDefinition | None = None
    conversation_state: ConversationState = Field(default_factory=ConversationState)


class WorkflowAssistantResponse(BaseModel):
    mode: AssistantMode
    assistant_message: str = Field(min_length=1, max_length=4000)
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    definition: WorkflowDefinition | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    change_summary: str | None = Field(default=None, min_length=1, max_length=500)


class AIChatHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=120)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10000)
    timestamp: str = Field(min_length=1, max_length=100)


class AIChatHistoryUpsertRequest(BaseModel):
    messages: list[AIChatHistoryMessage] = Field(default_factory=list, max_length=400)
    conversation_state: dict[str, Any] = Field(default_factory=dict)


class AIChatHistoryResponse(BaseModel):
    scope_key: str = Field(min_length=1, max_length=120)
    messages: list[AIChatHistoryMessage] = Field(default_factory=list)
    conversation_state: dict[str, Any] = Field(default_factory=dict)


class AIChatHistoryClearResponse(BaseModel):
    message: str
    deleted_messages: int = Field(ge=0)
    deleted_states: int = Field(ge=0)
