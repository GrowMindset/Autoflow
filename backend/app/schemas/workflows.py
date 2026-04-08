from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowNodePosition(BaseModel):
    x: float | int
    y: float | int


class WorkflowNodeDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    position: WorkflowNodePosition
    config: dict[str, Any]


class WorkflowEdgeDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    branch: str | None = Field(default=None, max_length=100)


class WorkflowDefinition(BaseModel):
    nodes: list[WorkflowNodeDefinition]
    edges: list[WorkflowEdgeDefinition]

    @model_validator(mode="after")
    def validate_graph(self) -> "WorkflowDefinition":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Workflow definition contains duplicate node ids")

        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("Workflow definition contains duplicate edge ids")

        node_id_set = set(node_ids)
        for edge in self.edges:
            if edge.source not in node_id_set or edge.target not in node_id_set:
                raise ValueError("Workflow definition contains edges with unknown nodes")
        return self


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    definition: WorkflowDefinition


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    definition: WorkflowDefinition | None = None
    is_published: bool | None = None

    @model_validator(mode="after")
    def ensure_any_field_present(self) -> "WorkflowUpdate":
        if self.model_fields_set:
            return self
        raise ValueError("At least one field must be provided")


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str | None
    definition: WorkflowDefinition
    is_published: bool
    created_at: datetime
    updated_at: datetime


class WorkflowListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str | None
    is_published: bool
    created_at: datetime
    updated_at: datetime


class WorkflowListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    next_cursor: str | None = None
    workflows: list[WorkflowListItem]


class WorkflowDeleteResponse(BaseModel):
    message: str
