from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


ExecutionStatus = Literal[
    "PENDING",
    "QUEUED",
    "WAITING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "BLOCKED",
    "SKIPPED",
]
TriggeredBy = str


class LoopControlOverride(BaseModel):
    enabled: bool | None = None
    max_node_executions: int | None = None
    max_total_node_executions: int | None = None


class RunFormRequest(BaseModel):
    form_data: dict[str, Any]
    start_node_id: str | None = None
    loop_control_override: LoopControlOverride | None = None


class PublicFormSubmitRequest(BaseModel):
    form_data: dict[str, Any]


class RunWorkflowRequest(BaseModel):
    start_node_id: str | None = None
    loop_control_override: LoopControlOverride | None = None


class RunScheduleRequest(BaseModel):
    start_node_id: str | None = None
    respect_schedule: bool = False
    loop_control_override: LoopControlOverride | None = None


class RunNodeTestRequest(BaseModel):
    input_data: dict[str, Any] | None = None


class ExecutionEnqueueResponse(BaseModel):
    execution_id: UUID
    workflow_id: UUID
    status: ExecutionStatus
    triggered_by: TriggeredBy


class WebhookEnqueueResponse(BaseModel):
    execution_id: UUID
    message: str


class PublicFormField(BaseModel):
    name: str
    label: str
    type: str
    required: bool = False


class PublicFormDefinitionResponse(BaseModel):
    workflow_id: UUID
    workflow_name: str
    path_token: str
    submit_url: str
    form_node_id: str
    form_title: str
    form_description: str
    fields: list[PublicFormField]


class NodeExecutionResult(BaseModel):
    node_id: str
    node_type: str
    status: ExecutionStatus
    input_data: dict[str, Any] | list[Any] | None
    output_data: dict[str, Any] | list[Any] | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class ExecutionDetailResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    user_id: UUID
    status: ExecutionStatus
    triggered_by: TriggeredBy
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    node_results: list[NodeExecutionResult]


class ExecutionListItem(BaseModel):
    id: UUID
    workflow_id: UUID
    workflow_name: str
    status: ExecutionStatus
    triggered_by: TriggeredBy
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


class ExecutionListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    executions: list[ExecutionListItem]
