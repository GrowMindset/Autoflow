from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


ExecutionStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
TriggeredBy = str


class RunFormRequest(BaseModel):
    form_data: dict[str, str]


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
