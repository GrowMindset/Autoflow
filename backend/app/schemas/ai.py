from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.workflows import WorkflowDefinition


class GenerateWorkflowRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1500)


class GenerateWorkflowResponse(BaseModel):
    definition: WorkflowDefinition
    name: str | None = Field(default=None, min_length=1, max_length=100)


class AIErrorDetail(BaseModel):
    code: str
    message: str
