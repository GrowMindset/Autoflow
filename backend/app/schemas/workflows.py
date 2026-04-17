from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


NODE_CONFIG_DEFAULTS: dict[str, dict[str, Any]] = {
    "manual_trigger": {},
    "form_trigger": {
        "form_title": "Form Submission",
        "form_description": "",
        "fields": [
            {
                "name": "email",
                "label": "Email",
                "type": "email",
                "required": True,
            }
        ],
    },
    "webhook_trigger": {
        "path": "",
        "method": "POST",
    },
    "schedule_trigger": {
        "timezone": "UTC",
        "enabled": True,
        "rules": [
            {
                "id": "rule_1",
                "interval": "hours",
                "every": 1,
                "trigger_minute": 0,
                "enabled": True,
            }
        ],
    },
    "workflow_trigger": {},
    "get_gmail_message": {
        "credential_id": "",
        "folder": "INBOX",
        "query": "",
        "limit": "10",
        "unread_only": False,
        "include_body": False,
        "mark_as_read": False,
    },
    "send_gmail_message": {
        "credential_id": "",
        "to": "",
        "cc": "",
        "bcc": "",
        "reply_to": "",
        "subject": "",
        "body": "",
        "is_html": False,
    },
    "create_google_sheets": {
        "credential_id": "",
        "title": "",
        "sheet_name": "",
    },
    "search_update_google_sheets": {
        "credential_id": "",
        "spreadsheet_id": "",
        "sheet_name": "",
        "search_column": "",
        "search_value": "",
        "update_mappings": [],
        "update_column": "",
        "update_value": "",
        "auto_create_headers": True,
        "upsert_if_not_found": False,
    },
    "create_google_docs": {
        "credential_id": "",
        "title": "",
        "initial_content": "",
    },
    "update_google_docs": {
        "credential_id": "",
        "document_id": "",
        "operation": "append_text",
        "text": "",
        "match_text": "",
        "match_case": False,
    },
    "telegram": {
        "credential_id": "",
        "message": "",
        "parse_mode": "",
    },
    "whatsapp": {
        "credential_id": "",
        "to_number": "",
        "template_name": "",
        "template_params": [],
        "language_code": "en_US",
    },
    "linkedin": {
        "content": "",
        "visibility": "",
    },
    "if_else": {
        "field": "",
        "operator": "equals",
        "value": "",
    },
    "switch": {
        "field": "",
        "cases": [],
        "default_case": "default",
    },
    "merge": {},
    "filter": {
        "input_key": "",
        "field": "",
        "operator": "equals",
        "value": "",
    },
    "delay": {
        "amount": "1",
        "unit": "minutes",
        "until_datetime": "",
    },
    "datetime_format": {
        "field": "",
        "output_format": "%Y-%m-%d",
    },
    "split_in": {
        "input_key": "",
    },
    "split_out": {
        "output_key": "results",
    },
    "aggregate": {
        "input_key": "",
        "field": "",
        "operation": "sum",
        "output_key": "",
    },
    "ai_agent": {
        "system_prompt": "",
        "command": "",
        "response_enhancement": "auto",
    },
    "chat_model_openai": {
        "credential_id": "",
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": None,
    },
    "chat_model_groq": {
        "credential_id": "",
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.7,
        "max_tokens": None,
    },
}


class WorkflowNodePosition(BaseModel):
    x: float | int
    y: float | int


class WorkflowNodeDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    position: WorkflowNodePosition
    config: dict[str, Any]

    @model_validator(mode="after")
    def normalize_config(self) -> "WorkflowNodeDefinition":
        defaults = NODE_CONFIG_DEFAULTS.get(self.type)
        if defaults is None:
            return self

        self.config = {
            **defaults,
            **self.config,
        }
        return self


class WorkflowEdgeDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    sourceHandle: str | None = Field(default=None, max_length=100)
    targetHandle: str | None = Field(default=None, max_length=100)
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
        nodes_by_id = {node.id: node for node in self.nodes}
        for edge in self.edges:
            if edge.source not in node_id_set or edge.target not in node_id_set:
                raise ValueError("Workflow definition contains edges with unknown nodes")

            source_node = nodes_by_id[edge.source]
            if source_node.type == "if_else" and edge.branch not in {None, "true", "false"}:
                raise ValueError(
                    "Workflow definition contains invalid if_else branch labels"
                )
            if source_node.type == "switch":
                switch_cases = source_node.config.get("cases", [])
                allowed_branches = {
                    case.get("label")
                    for case in switch_cases
                    if isinstance(case, dict) and case.get("label")
                }
                default_case = source_node.config.get("default_case")
                if default_case:
                    allowed_branches.add(default_case)
                if edge.branch is not None and edge.branch not in allowed_branches:
                    raise ValueError(
                        "Workflow definition contains switch edges with unknown branch labels"
                    )
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


class WorkflowWebhookEndpoint(BaseModel):
    node_id: str
    path_token: str
    is_active: bool
    method: str
    path: str
    url: str


class WorkflowWebhookListResponse(BaseModel):
    webhooks: list[WorkflowWebhookEndpoint]
