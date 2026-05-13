from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.form_fields import normalize_form_field_config


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
    "workflow_trigger": {
        "input_data_mode": "accept_all",
        "input_schema": [],
        "json_example": "",
    },
    "execute_workflow": {
        "source": "database",
        "workflow_id": "",
        "workflow_json": "",
        "workflow_inputs": [],
        "mode": "run_once",
    },
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
    "create_gmail_draft": {
        "credential_id": "",
        "to": "",
        "subject": "",
        "body": "",
    },
    "add_gmail_label": {
        "credential_id": "",
        "message_id": "",
        "label_name": "",
    },
    "create_google_sheets": {
        "credential_id": "",
        "title": "",
        "sheet_name": "",
        "columns": [],
    },
    "read_google_sheets": {
        "credential_id": "",
        "spreadsheet_source_type": "id",
        "spreadsheet_id": "",
        "spreadsheet_url": "",
        "sheet_name": "Sheet1",
        "range": "",
        "first_row_as_header": True,
        "include_empty_rows": False,
        "max_rows": "",
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
    "read_google_docs": {
        "credential_id": "",
        "document_source_type": "id",
        "document_id": "",
        "document_url": "",
        "max_characters": "",
        "include_raw_json": False,
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
        "condition_type": "AND",
        "conditions": [
            {
                "field": "",
                "operator": "equals",
                "value": "",
                "value_mode": "literal",
                "value_field": "",
                "case_sensitive": True,
            }
        ],
        # Legacy single-condition keys (kept for backward compatibility).
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
        "logic": "and",
        "conditions": [],
        # Legacy single-condition keys (kept for backward compatibility).
        "field": "",
        "operator": "equals",
        "value": "",
        "value_mode": "literal",
        "value_field": "",
        "case_sensitive": True,
    },
    "limit": {
        "input_key": "",
        "limit": 10,
        "offset": 0,
        "start_from": "start",
    },
    "sort": {
        "input_key": "",
        "sort_by": "",
        "order": "asc",
        "data_type": "auto",
        "nulls": "last",
        "case_sensitive": False,
    },
    "delay": {
        "wait_mode": "after_interval",
        "amount": "1",
        "unit": "minutes",
        "until_datetime": "",
        "timezone": "Asia/Kolkata",
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
    "code": {
        "language": "python",
        "code": "# input_data is available as a dict\n# assign your result to: output\noutput = input_data",
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


FILTER_LOGIC_VALUES = {"and", "or"}
FILTER_DATA_TYPES = {"string", "number", "boolean", "date", "array", "object"}
FILTER_OPERATORS_BY_DATA_TYPE: dict[str, tuple[str, ...]] = {
    "string": (
        "exists",
        "does_not_exist",
        "is_empty",
        "is_not_empty",
        "equals",
        "not_equals",
        "contains",
        "not_contains",
        "starts_with",
        "does_not_start_with",
        "ends_with",
        "does_not_end_with",
        "matches_regex",
        "does_not_match_regex",
    ),
    "number": (
        "exists",
        "does_not_exist",
        "is_empty",
        "is_not_empty",
        "equals",
        "not_equals",
        "greater_than",
        "less_than",
        "greater_than_or_equals",
        "less_than_or_equals",
    ),
    "boolean": (
        "exists",
        "does_not_exist",
        "is_empty",
        "is_not_empty",
        "is_true",
        "is_false",
        "equals",
        "not_equals",
    ),
    "date": (
        "exists",
        "does_not_exist",
        "is_empty",
        "is_not_empty",
        "equals",
        "not_equals",
        "after",
        "before",
        "after_or_equal",
        "before_or_equal",
    ),
    "array": (
        "exists",
        "does_not_exist",
        "is_empty",
        "is_not_empty",
        "contains",
        "not_contains",
        "length_equals",
        "length_not_equals",
        "length_greater_than",
        "length_less_than",
        "length_greater_than_or_equals",
        "length_less_than_or_equals",
    ),
    "object": (
        "exists",
        "does_not_exist",
        "is_empty",
        "is_not_empty",
        "equals",
        "not_equals",
    ),
}
FILTER_OPERATOR_ALIASES = {
    "not_exists": "does_not_exist",
    "greater_than_or_equal": "greater_than_or_equals",
    "less_than_or_equal": "less_than_or_equals",
}
FILTER_VALUE_MODES = {"literal", "field"}
FILTER_KNOWN_KEYS = {
    "input_key",
    "logic",
    "condition_logic",
    "conditions",
    "field",
    "operator",
    "data_type",
    "value",
    "value_mode",
    "value_field",
    "case_sensitive",
}

IF_ELSE_CONDITION_TYPES = {"AND", "OR"}
IF_ELSE_KNOWN_KEYS = {
    "condition_type",
    "conditions",
    "field",
    "operator",
    "value",
    "value_mode",
    "value_field",
    "case_sensitive",
}


def _normalize_filter_condition(raw_condition: Any, *, index: int) -> dict[str, Any] | None:
    if not isinstance(raw_condition, dict):
        return None

    field = str(raw_condition.get("field") or "").strip()
    operator_raw = str(raw_condition.get("operator") or "equals").strip().lower()
    operator_normalized = FILTER_OPERATOR_ALIASES.get(operator_raw, operator_raw)
    raw_data_type = str(raw_condition.get("data_type") or "").strip().lower()
    if raw_data_type in FILTER_DATA_TYPES:
        data_type = raw_data_type
    elif operator_normalized in {
        "greater_than",
        "less_than",
        "greater_than_or_equals",
        "less_than_or_equals",
    }:
        data_type = "number"
    elif operator_normalized in {
        "after",
        "before",
        "after_or_equal",
        "before_or_equal",
        "is_after",
        "is_before",
        "is_after_or_equal",
        "is_before_or_equal",
    }:
        data_type = "date"
    elif operator_normalized in {
        "length_equals",
        "length_not_equals",
        "length_greater_than",
        "length_less_than",
        "length_greater_than_or_equals",
        "length_less_than_or_equals",
    }:
        data_type = "array"
    elif operator_normalized in {"is_true", "is_false"}:
        data_type = "boolean"
    else:
        data_type = "string"
    allowed_operators = FILTER_OPERATORS_BY_DATA_TYPE.get(data_type, FILTER_OPERATORS_BY_DATA_TYPE["string"])
    operator = operator_normalized if operator_normalized in allowed_operators else "equals"
    value_mode_raw = str(raw_condition.get("value_mode") or "literal").strip().lower()
    value_mode = value_mode_raw if value_mode_raw in FILTER_VALUE_MODES else "literal"
    value_field = str(raw_condition.get("value_field") or "").strip()
    join_with_previous_raw = str(
        raw_condition.get("join_with_previous")
        or raw_condition.get("condition")
        or raw_condition.get("logic")
        or "and"
    ).strip().lower()
    join_with_previous = "or" if join_with_previous_raw == "or" else "and"

    normalized: dict[str, Any] = {
        "id": str(raw_condition.get("id") or f"condition_{index}").strip() or f"condition_{index}",
        "field": field,
        "operator": operator,
        "data_type": data_type,
        "value_mode": value_mode,
        "value_field": value_field,
        "case_sensitive": _as_bool(raw_condition.get("case_sensitive"), default=True),
        "join_with_previous": "and" if index <= 1 else join_with_previous,
    }
    if value_mode == "field":
        normalized["value"] = ""
    else:
        normalized["value"] = raw_condition.get("value", "")
    return normalized


def _normalize_filter_config(config: dict[str, Any]) -> dict[str, Any]:
    safe_config = dict(config or {})
    input_key = str(safe_config.get("input_key") or "").strip()
    logic_raw = str(
        safe_config.get("logic")
        or safe_config.get("condition_logic")
        or "and"
    ).strip().lower()
    logic = logic_raw if logic_raw in FILTER_LOGIC_VALUES else "and"

    normalized_conditions: list[dict[str, Any]] = []
    raw_conditions = safe_config.get("conditions")
    if isinstance(raw_conditions, list):
        for idx, raw_condition in enumerate(raw_conditions, start=1):
            condition_data = raw_condition if isinstance(raw_condition, dict) else {}
            if idx > 1 and "join_with_previous" not in condition_data:
                condition_data = {
                    **condition_data,
                    "join_with_previous": logic,
                }
            normalized = _normalize_filter_condition(condition_data, index=idx)
            if normalized is not None:
                normalized_conditions.append(normalized)

    if not normalized_conditions:
        legacy_condition = _normalize_filter_condition(
            {
                "field": safe_config.get("field"),
                "operator": safe_config.get("operator"),
                "value": safe_config.get("value", ""),
                "value_mode": safe_config.get("value_mode"),
                "value_field": safe_config.get("value_field"),
                "case_sensitive": safe_config.get("case_sensitive", True),
                "join_with_previous": logic,
            },
            index=1,
        )
        has_legacy_signal = any(
            [
                str(safe_config.get("field") or "").strip(),
                str(safe_config.get("value_field") or "").strip(),
                "value" in safe_config,
            ]
        )
        if legacy_condition is not None and has_legacy_signal:
            normalized_conditions.append(legacy_condition)

    if not normalized_conditions:
        normalized_conditions.append(
            {
                "id": "condition_1",
                "field": "",
                "operator": "equals",
                "value_mode": "literal",
                "value_field": "",
                "value": "",
                "case_sensitive": True,
                "data_type": "string",
                "join_with_previous": "and",
            }
        )

    pruned: dict[str, Any] = {
        key: value
        for key, value in safe_config.items()
        if key not in FILTER_KNOWN_KEYS
    }
    pruned["input_key"] = input_key
    pruned["logic"] = logic
    pruned["conditions"] = normalized_conditions
    return pruned


def _normalize_if_else_condition(raw_condition: Any, *, index: int) -> dict[str, Any] | None:
    if not isinstance(raw_condition, dict):
        return None

    field = str(raw_condition.get("field") or "").strip()
    operator_raw = str(raw_condition.get("operator") or "equals").strip().lower()
    operator = FILTER_OPERATOR_ALIASES.get(operator_raw, operator_raw)
    if operator not in SHARED_IF_ELSE_OPERATORS:
        operator = "equals"

    value_mode_raw = str(raw_condition.get("value_mode") or "literal").strip().lower()
    value_mode = value_mode_raw if value_mode_raw in FILTER_VALUE_MODES else "literal"
    value_field = str(raw_condition.get("value_field") or "").strip()

    normalized: dict[str, Any] = {
        "id": str(raw_condition.get("id") or f"condition_{index}").strip() or f"condition_{index}",
        "field": field,
        "operator": operator,
        "value_mode": value_mode,
        "value_field": value_field,
        "case_sensitive": _as_bool(raw_condition.get("case_sensitive"), default=True),
    }
    normalized["value"] = "" if value_mode == "field" else raw_condition.get("value", "")
    return normalized


SHARED_IF_ELSE_OPERATORS = {
    "equals",
    "not_equals",
    "greater_than",
    "less_than",
    "contains",
    "not_contains",
}


def _normalize_if_else_config(config: dict[str, Any]) -> dict[str, Any]:
    safe_config = dict(config or {})
    condition_type_raw = str(safe_config.get("condition_type") or "AND").strip().upper()
    condition_type = condition_type_raw if condition_type_raw in IF_ELSE_CONDITION_TYPES else "AND"
    has_legacy_signal = any(
        [
            str(safe_config.get("field") or "").strip(),
            str(safe_config.get("value_field") or "").strip(),
            "value" in safe_config and str(safe_config.get("value") or "").strip(),
        ]
    )

    normalized_conditions: list[dict[str, Any]] = []
    raw_conditions = safe_config.get("conditions")
    if isinstance(raw_conditions, list):
        for idx, raw_condition in enumerate(raw_conditions, start=1):
            normalized = _normalize_if_else_condition(raw_condition, index=idx)
            if normalized is not None:
                normalized_conditions.append(normalized)

    if (
        has_legacy_signal
        and len(normalized_conditions) == 1
        and not str(normalized_conditions[0].get("field") or "").strip()
    ):
        normalized_conditions = []

    if not normalized_conditions:
        legacy_condition = _normalize_if_else_condition(
            {
                "field": safe_config.get("field"),
                "operator": safe_config.get("operator"),
                "value": safe_config.get("value", ""),
                "value_mode": safe_config.get("value_mode"),
                "value_field": safe_config.get("value_field"),
                "case_sensitive": safe_config.get("case_sensitive", True),
            },
            index=1,
        )
        if legacy_condition is not None:
            normalized_conditions.append(legacy_condition)

    if not normalized_conditions:
        normalized_conditions.append(
            {
                "id": "condition_1",
                "field": "",
                "operator": "equals",
                "value": "",
                "value_mode": "literal",
                "value_field": "",
                "case_sensitive": True,
            }
        )

    pruned: dict[str, Any] = {
        key: value
        for key, value in safe_config.items()
        if key not in IF_ELSE_KNOWN_KEYS
    }
    pruned["condition_type"] = condition_type
    pruned["conditions"] = normalized_conditions
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
    is_active: bool = True

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

        if self.type == "filter":
            self.config = _normalize_filter_config(self.config)

        if self.type == "if_else":
            self.config = _normalize_if_else_config(self.config)

        if self.type == "form_trigger":
            raw_fields = self.config.get("fields", [])
            normalized_fields: list[dict[str, Any]] = []
            if isinstance(raw_fields, list):
                for index, raw_field in enumerate(raw_fields):
                    field = normalize_form_field_config(raw_field, index=index)
                    if field is not None:
                        normalized_fields.append(field)
            self.config["fields"] = normalized_fields

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
        workflow_trigger_count = sum(
            1 for node in self.nodes if node.type == "workflow_trigger"
        )
        if workflow_trigger_count > 1:
            raise ValueError("Workflow can only contain one workflow_trigger node")

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

        for node in self.nodes:
            if node.type != "execute_workflow":
                continue
            source = str(node.config.get("source") or "database").strip().lower()
            if source == "json":
                workflow_json = node.config.get("workflow_json")
                if isinstance(workflow_json, str):
                    if not workflow_json.strip():
                        raise ValueError(
                            "execute_workflow requires valid workflow_json when source=json"
                        )
                    try:
                        json.loads(workflow_json)
                    except Exception as exc:
                        raise ValueError(
                            "execute_workflow workflow_json must be valid JSON"
                        ) from exc
                elif not isinstance(workflow_json, dict):
                    raise ValueError(
                        "execute_workflow requires valid workflow_json when source=json"
                    )
            else:
                # Draft parent workflows may be generated before the child workflow exists.
                # Runtime execution still requires a concrete workflow_id.
                node.config["workflow_id"] = str(node.config.get("workflow_id") or "").strip()
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


class WorkflowVersionCreate(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class WorkflowVersionSnapshot(BaseModel):
    name: str
    description: str | None
    definition: WorkflowDefinition


class WorkflowVersionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    created_by: UUID
    version_number: int
    note: str | None
    created_at: datetime


class WorkflowVersionResponse(WorkflowVersionListItem):
    snapshot_json: WorkflowVersionSnapshot


class WorkflowVersionListResponse(BaseModel):
    versions: list[WorkflowVersionListItem]
