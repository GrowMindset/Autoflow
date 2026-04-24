from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
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
        "timezone": "Asia/Kolkata",
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
        "image": "",
        "is_html": False,
    },
    "create_google_sheets": {
        "credential_id": "",
        "title": "",
        "sheet_name": "",
        "columns": [],
    },
    "search_update_google_sheets": {
        "credential_id": "",
        "spreadsheet_source_type": "id",
        "spreadsheet_id": "",
        "spreadsheet_url": "",
        "sheet_name": "",
        "operation": "upsert_row",
        "key_column": "",
        "key_value": "",
        "append_columns": [],
        "append_values": [],
        "search_column": "",
        "search_value": "",
        "update_mappings": [],
        "columns_to_add": [],
        "columns_to_delete": [],
        "ensure_columns": [],
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
        "image": "",
        "match_text": "",
        "match_case": False,
    },
    "telegram": {
        "credential_id": "",
        "message": "",
        "image": "",
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
        "credential_id": "",
        "post_text": "",
        "image": "",
        "visibility": "PUBLIC",
    },
    "http_request": {
        "url": "",
        "method": "GET",
        "auth_mode": "none",
        "credential_id": "",
        "bearer_token": "",
        "bearer_prefix": "Bearer",
        "username": "",
        "password": "",
        "api_key_name": "x-api-key",
        "api_key_value": "",
        "api_key_in": "header",
        "api_key_prefix": "",
        "headers_json": "{}",
        "query_json": "{}",
        "body_type": "none",
        "body_json": "{}",
        "body_form_json": "{}",
        "body_raw": "",
        "timeout_seconds": 30,
        "follow_redirects": True,
        "continue_on_fail": False,
        "response_format": "auto",
    },
    "file_read": {
        "file_path": "",
        "parse_as": "auto",
        "encoding": "utf-8",
        "max_bytes": 5242880,
        "include_metadata": True,
        "csv_delimiter": "",
    },
    "file_write": {
        "file_path": "",
        "content_source": "input",
        "input_key": "",
        "content_text": "",
        "input_format": "auto",
        "write_mode": "create",
        "encoding": "utf-8",
        "create_dirs": True,
    },
    "slack_send_message": {
        "credential_id": "",
        "webhook_url": "",
        "channel": "",
        "message": "",
    },
    "if_else": {
        "field": "",
        "operator": "equals",
        "value": "",
        "value_mode": "literal",
        "value_field": "",
        "case_sensitive": True,
    },
    "switch": {
        "field": "",
        "cases": [],
        "default_case": "default",
    },
    "merge": {
        "mode": "append",
        "input_count": 2,
        "choose_branch": "input1",
        "output_key": "merged",
        "input_1_handle": "input1",
        "input_2_handle": "input2",
        "join_type": "inner",
        "input_1_field": "",
        "input_2_field": "",
    },
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
    "image_gen": {
        "credential_id": "",
        "model": "dall-e-3",
        "prompt": "",
        "size": "1024x1024",
        "quality": "standard",
        "style": "vivid",
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

MERGE_MODE_ALIASES: dict[str, str] = {
    "choose_input1": "choose_input_1",
    "choose_input_1": "choose_input_1",
    "choose_input2": "choose_input_2",
    "choose_input_2": "choose_input_2",
    "choose_input": "choose_branch",
    "choose": "choose_branch",
    "passthrough": "choose_input_1",
    "pass_through": "choose_input_1",
    "pass-through": "choose_input_1",
    "pass": "choose_input_1",
}
MERGE_OUTPUT_MODES = {"append", "combine_by_position", "combine_by_fields"}
MERGE_JOIN_TYPES = {"inner", "left", "right", "outer"}
MERGE_KNOWN_KEYS = {
    "mode",
    "input_count",
    "choose_branch",
    "output_key",
    "input_1_handle",
    "input_2_handle",
    "join_type",
    "input_1_field",
    "input_2_field",
    "allow_missing_branch_fallback",
}


def _normalize_merge_mode(raw_mode: Any) -> str:
    mode = str(raw_mode or "append").strip().lower()
    if not mode:
        return "append"
    return MERGE_MODE_ALIASES.get(mode, mode)


def _normalize_merge_input_count(raw_count: Any) -> int:
    try:
        parsed = int(raw_count)
    except Exception:
        return 2
    return min(6, max(2, parsed))


def _as_bool(raw_value: Any, *, default: bool = False) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, (int, float)):
        return bool(raw_value)
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_and_prune_merge_config(config: dict[str, Any]) -> dict[str, Any]:
    safe_config = dict(config or {})
    mode = _normalize_merge_mode(safe_config.get("mode"))
    input_count = _normalize_merge_input_count(safe_config.get("input_count"))
    choose_branch_raw = str(safe_config.get("choose_branch") or "").strip().lower()
    choose_branch = choose_branch_raw or (
        "input2" if mode == "choose_input_2" else "input1"
    )
    output_key = str(safe_config.get("output_key") or "").strip() or "merged"
    input_1_handle = str(safe_config.get("input_1_handle") or "input1").strip() or "input1"
    input_2_handle = str(safe_config.get("input_2_handle") or "input2").strip() or "input2"
    join_type_raw = str(safe_config.get("join_type") or "inner").strip().lower()
    join_type = join_type_raw if join_type_raw in MERGE_JOIN_TYPES else "inner"

    pruned: dict[str, Any] = {
        key: value
        for key, value in safe_config.items()
        if key not in MERGE_KNOWN_KEYS
    }
    pruned["mode"] = mode
    pruned["input_count"] = input_count
    if _as_bool(safe_config.get("allow_missing_branch_fallback"), default=False):
        pruned["allow_missing_branch_fallback"] = True

    if mode == "choose_branch":
        pruned["choose_branch"] = choose_branch
        return pruned

    if mode == "choose_input_1":
        pruned["input_1_handle"] = input_1_handle
        return pruned

    if mode == "choose_input_2":
        pruned["input_2_handle"] = input_2_handle
        return pruned

    if mode in MERGE_OUTPUT_MODES:
        pruned["output_key"] = output_key

    if mode in {"combine_by_position", "combine_by_fields"}:
        pruned["join_type"] = join_type
        pruned["input_1_handle"] = input_1_handle
        pruned["input_2_handle"] = input_2_handle

    if mode == "combine_by_fields":
        pruned["input_1_field"] = str(safe_config.get("input_1_field") or "").strip()
        pruned["input_2_field"] = str(safe_config.get("input_2_field") or "").strip()

    return pruned


IMAGE_GEN_SIZES_BY_MODEL: dict[str, set[str]] = {
    "dall-e-3": {"1024x1024", "1792x1024", "1024x1792"},
    "dall-e-2": {"256x256", "512x512", "1024x1024"},
    "gpt-image-1": {"1024x1024", "1536x1024", "1024x1536"},
}


class ImageGenNodeConfig(BaseModel):
    credential_id: str = ""
    model: Literal["gpt-image-1", "dall-e-3", "dall-e-2"] = "dall-e-3"
    prompt: str = Field(min_length=1)
    size: str = "1024x1024"
    quality: Literal["standard", "hd"] = "standard"
    style: Literal["vivid", "natural"] = "vivid"

    @model_validator(mode="after")
    def validate_model_size(self) -> "ImageGenNodeConfig":
        if self.size not in IMAGE_GEN_SIZES_BY_MODEL[self.model]:
            allowed = ", ".join(sorted(IMAGE_GEN_SIZES_BY_MODEL[self.model]))
            raise ValueError(
                f"Image Gen size '{self.size}' is invalid for {self.model}. Use one of: {allowed}."
            )
        return self


NODE_CONFIG_SCHEMAS = {
    "image_gen": ImageGenNodeConfig,
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

        schema = NODE_CONFIG_SCHEMAS.get(self.type)
        if schema is not None:
            self.config = schema(**self.config).model_dump()

        if self.type == "switch":
            raw_cases = self.config.get("cases", [])
            normalized_cases: list[dict[str, Any]] = []
            if isinstance(raw_cases, list):
                for idx, raw_case in enumerate(raw_cases):
                    if not isinstance(raw_case, dict):
                        continue
                    case = dict(raw_case)
                    label = str(case.get("label") or "").strip()
                    case_id = str(case.get("id") or "").strip()
                    if not case_id:
                        case_id = label or f"case_{idx + 1}"
                    case["id"] = case_id
                    case["label"] = label
                    normalized_cases.append(case)
            self.config["cases"] = normalized_cases
            default_case = str(self.config.get("default_case") or "").strip()
            self.config["default_case"] = default_case or "default"

        if self.type == "merge":
            self.config = _normalize_and_prune_merge_config(self.config)

        return self


class WorkflowEdgeDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=100)
    sourceHandle: str | None = Field(default=None, max_length=100)
    targetHandle: str | None = Field(default=None, max_length=100)
    branch: str | None = Field(default=None, max_length=100)


class WorkflowLoopControl(BaseModel):
    enabled: bool = False
    max_node_executions: int = Field(default=3, ge=1, le=10000)
    max_total_node_executions: int = Field(default=500, ge=1, le=200000)


class WorkflowDefinition(BaseModel):
    nodes: list[WorkflowNodeDefinition]
    edges: list[WorkflowEdgeDefinition]
    loop_control: WorkflowLoopControl = Field(default_factory=WorkflowLoopControl)

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
            if source_node.type == "if_else":
                branch = edge.branch if edge.branch is not None else edge.sourceHandle
                branch_value = str(branch or "").strip()
                if branch_value not in {"true", "false"}:
                    raise ValueError(
                        "Workflow definition contains invalid if_else branch labels"
                    )
                edge.branch = branch_value
                edge.sourceHandle = branch_value

            if source_node.type == "switch":
                switch_cases = source_node.config.get("cases", [])
                label_to_id = {
                    str(case.get("label") or "").strip(): str(case.get("id") or "").strip()
                    for case in switch_cases
                    if isinstance(case, dict)
                    and str(case.get("label") or "").strip()
                    and str(case.get("id") or "").strip()
                }
                allowed_branches = {
                    str(case.get("id") or "").strip()
                    for case in switch_cases
                    if isinstance(case, dict) and str(case.get("id") or "").strip()
                }
                default_case = str(source_node.config.get("default_case") or "").strip()
                if default_case:
                    allowed_branches.add(default_case)

                branch = edge.branch if edge.branch is not None else edge.sourceHandle
                branch_value = str(branch or "").strip()
                if branch_value in label_to_id:
                    branch_value = label_to_id[branch_value]

                if branch_value not in allowed_branches:
                    raise ValueError(
                        "Workflow definition contains switch edges with unknown branch ids"
                    )
                edge.branch = branch_value
                edge.sourceHandle = branch_value
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
    is_active: bool | None = None

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
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WorkflowListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str | None
    is_published: bool
    is_active: bool
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
