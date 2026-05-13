from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from app.services.llm_providers import BaseLLMProvider, get_provider

from app.execution.dag_executor import TRIGGER_NODE_TYPES
from app.schemas.workflows import NODE_CONFIG_DEFAULTS, WorkflowDefinition

load_dotenv()

SHARED_OPERATORS = (
    "equals",
    "not_equals",
    "greater_than",
    "less_than",
    "contains",
    "not_contains",
)

AI_CHAT_MODEL_NODE_TYPES = {"chat_model_openai", "chat_model_groq"}
TEMPLATE_SINGLE_BRACE_PATTERN = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_.]*)\}(?!\})")
TEMPLATE_DOUBLE_BRACE_PATTERN = re.compile(r"\{\{\s*(.+?)\s*\}\}")
SEQUENCE_DAYS_PATTERN = re.compile(
    r"\b(\d{1,2})\s*-\s*day(?:s)?\b|\b(\d{1,2})\s*day(?:s)?\b"
)
IMAGE_GENERATION_HINTS = (
    "generate image",
    "generate an image",
    "create image",
    "create an image",
    "make image",
    "make an image",
    "generate photo",
    "generate a photo",
    "create photo",
    "create a photo",
    "generate picture",
    "generate a picture",
    "create picture",
    "create a picture",
    "generate illustration",
    "create illustration",
    "image generation",
    "ai image",
    "generated visual",
    "ai visual",
)

SUB_WORKFLOW_RESPONSE_MESSAGE = (
    "I've generated your parent workflow.\n\n"
    "To complete the setup:\n"
    "1. Accept and save this parent workflow first\n"
    "2. Click 'New Workflow' in the sidebar to open a fresh canvas\n"
    "3. Come back to this chat and describe what the child workflow should do\n"
    "4. Once the child is saved, open the Execute Workflow node in the parent and select the child workflow from the dropdown\n\n"
    "Ready when you are — describe the child workflow."
)

SUB_WORKFLOW_INTENT_HINTS = (
    "call a sub-workflow",
    "call a sub workflow",
    "call another workflow",
    "calling one workflow from another",
    "one workflow from another",
    "trigger another workflow",
    "run another workflow",
    "reuse workflow",
    "inside another workflow",
    "run a child workflow",
    "child workflow",
    "sub-workflow",
    "sub workflow",
    "trigger a sub-process",
    "trigger sub-process",
    "trigger a sub process",
    "sub-process",
    "sub process",
    "subprocess workflow",
    "sub-process workflow",
    "execute a workflow within a workflow",
    "execute workflow within workflow",
    "workflow inside workflow",
    "workflow from another workflow",
)

TRIGGER_KEYWORD_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "workflow_trigger",
        (
            "workflow trigger",
            "workflow_trigger",
            "from another workflow",
            "parent workflow",
            "upstream workflow",
        ),
    ),
    (
        "schedule_trigger",
        (
            "schedule trigger",
            "schedule_trigger",
            "cron",
            "hourly",
            "daily",
            "weekly",
            "monthly",
            "every ",
            "each day",
        ),
    ),
    (
        "form_trigger",
        (
            "form trigger",
            "form_trigger",
            "form submission",
            "submit form",
            "lead form",
            "contact form",
            "registration form",
            "survey form",
            "application form",
            "feedback form",
            "user input form",
        ),
    ),
    (
        "webhook_trigger",
        (
            "webhook",
            "webhook trigger",
            "webhook_trigger",
            "endpoint",
            "api call",
            "http request",
            "callback",
            "incoming event",
            "incoming payload",
            "from api",
        ),
    ),
    (
        "manual_trigger",
        (
            "manual trigger",
            "manual_trigger",
            "manually",
            "run manually",
            "on demand",
            "run button",
            "click run",
            "test run",
        ),
    ),
)

EVENT_LANGUAGE_HINTS = (
    " when ",
    "whenever",
    "upon ",
    " on new ",
    "on each ",
    "once ",
)

FORM_INTENT_HINTS = (
    "lead",
    "signup",
    "sign up",
    "registration",
    "register",
    "contact us",
    "feedback",
    "survey",
    "application",
    "form",
    "submission",
)

WEBHOOK_SOURCE_HINTS = (
    "website",
    "api",
    "app",
    "service",
    "system",
    "crm",
    "erp",
    "shopify",
    "stripe",
    "hubspot",
    "salesforce",
    "callback",
    "payload",
    "event",
)

ASSISTANT_ACTION_HINTS = (
    "send",
    "post",
    "create",
    "update",
    "delete",
    "append",
    "upsert",
    "notify",
    "summarize",
    "classify",
    "analyze",
    "transform",
    "write",
    "read",
    "fetch",
    "generate",
    "route",
    "log",
    "nurture",
    "nurturing",
    "campaign",
    "follow-up",
    "follow up",
    "lead generation",
    "lead nurturing",
)

ASSISTANT_COMPLETION_HINTS = (
    "send",
    "post",
    "notify",
    "message",
    "email",
    "mail",
    "telegram",
    "whatsapp",
    "slack",
    "linkedin",
    "http",
    "api",
    "fetch",
    "read",
    "write",
    "update",
    "delete",
    "append",
    "upsert",
    "filter",
    "merge",
    "split",
    "delay",
    "route",
    "classify",
    "summarize",
    "analyze",
)

ASSISTANT_CHANNEL_HINTS: dict[str, tuple[str, ...]] = {
    "send_gmail_message": ("gmail", "g mail", "email", "e-mail", "mail"),
    "create_gmail_draft": ("gmail draft", "email draft", "draft email", "draft in gmail"),
    "add_gmail_label": ("gmail label", "email label", "label gmail", "label email"),
    "slack_send_message": ("slack",),
    "telegram": ("telegram", "telegarm", "telegrm"),
    "whatsapp": ("whatsapp", "watsapp", "whatapp", "whats app", "wa"),
    "linkedin": ("linkedin", "linked in", "linkdin", "likendin"),
    "create_google_sheets": ("sheet", "sheets", "spreadsheet"),
    "create_google_docs": ("doc", "docs", "document"),
    "read_google_docs": ("read doc", "read docs", "google doc", "google docs document"),
}

ASSISTANT_BRANCH_HINTS = (
    "if ",
    "if/else",
    "else",
    "otherwise",
    "condition",
    "branch",
    "path",
    "parallel",
)

ASSISTANT_MODIFY_HINTS = (
    "modify",
    "change",
    "edit",
    "refine",
    "tweak",
    "adjust",
    "remove",
    "replace",
    "add to existing",
    "update existing",
    "change existing",
    "current workflow",
    "this workflow",
)

ASSISTANT_TIMING_HINTS = (
    "schedule",
    "cron",
    "every",
    "daily",
    "weekly",
    "monthly",
    "hourly",
    "sequence",
    "follow-up",
)

ASSISTANT_TIMING_VALUE_PATTERN = re.compile(
    r"\bevery\s+(\d+\s*)?(minute|minutes|min|hour|hours|day|days|week|weeks|month|months)\b"
)

ASSISTANT_DATA_MAPPING_HINTS = (
    "{{",
    "field",
    "column",
    "input",
    "output",
    "subject",
    "message",
    "body",
    "status",
    "email",
    "phone",
)

ASSISTANT_SENSITIVE_CONFIG_KEYS = {
    "credential_id",
    "bearer_token",
    "password",
    "api_key_value",
    "username",
}

CHANNEL_DISPLAY_NAMES: dict[str, str] = {
    "send_gmail_message": "Gmail",
    "create_gmail_draft": "Gmail Draft",
    "add_gmail_label": "Gmail Label",
    "slack_send_message": "Slack",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "linkedin": "LinkedIn",
    "create_google_sheets": "Google Sheets",
    "create_google_docs": "Google Docs",
    "read_google_docs": "Google Docs",
}

ASK_NODE_MANUAL_ALIASES: dict[str, tuple[str, ...]] = {
    "http_request": ("http node", "api node", "http request node"),
    "send_gmail_message": ("gmail node", "email node", "mail node"),
    "create_gmail_draft": ("gmail draft node", "email draft node"),
    "add_gmail_label": ("gmail label node", "email label node"),
    "search_update_google_sheets": ("google sheets node", "sheets node", "sheet node"),
    "create_google_sheets": ("google sheets create", "create sheet"),
    "read_google_sheets": ("read google sheets", "google sheets read", "read sheet"),
    "read_google_docs": ("read google docs", "google docs read", "read doc"),
    "limit": ("limit node", "array limit"),
    "sort": ("sort node", "array sort"),
    "webhook_trigger": ("webhook", "webhook trigger"),
    "form_trigger": ("form trigger", "form submission node"),
    "schedule_trigger": ("schedule trigger", "cron trigger"),
    "manual_trigger": ("manual trigger", "run trigger"),
    "if_else": ("if else", "if/else"),
    "ai_agent": ("ai node", "ai agent"),
    "image_gen": ("image node", "image generation node"),
}

AI_AGENT_STRUCTURED_OUTPUT_KEYS = {
    "summary",
    "sentiment",
    "urgency_reason",
    "recommended_next_action",
    "confidence_score",
    "category",
    "intent",
    "label",
    "classification",
    "analysis",
    "reason",
    "score",
}

CREDENTIAL_TROUBLESHOOT_NODE_TYPES = {
    "http_request",
    "get_gmail_message",
    "send_gmail_message",
    "create_gmail_draft",
    "add_gmail_label",
    "create_google_sheets",
    "search_update_google_sheets",
    "read_google_sheets",
    "create_google_docs",
    "read_google_docs",
    "update_google_docs",
    "telegram",
    "whatsapp",
    "slack_send_message",
    "linkedin",
    "chat_model_openai",
    "chat_model_groq",
    "image_gen",
}

MAPPING_PASSTHROUGH_NODE_TYPES = {
    "merge",
    "if_else",
    "switch",
    "filter",
    "delay",
    "sort",
    "limit",
    "split_in",
    "split_out",
    "aggregate",
    "datetime_format",
    "code",
}

RELIABILITY_PATTERN_NODE_TYPES = {
    "http_request",
    "telegram",
    "whatsapp",
    "send_gmail_message",
    "create_gmail_draft",
    "add_gmail_label",
    "slack_send_message",
    "linkedin",
    "search_update_google_sheets",
    "create_google_sheets",
    "create_google_docs",
    "update_google_docs",
    "file_write",
}

PERFORMANCE_SENSITIVE_NODE_TYPES = {
    "http_request",
    "ai_agent",
    "image_gen",
    "code",
    "merge",
    "filter",
    "sort",
    "limit",
    "aggregate",
    "search_update_google_sheets",
    "read_google_sheets",
    "send_gmail_message",
    "create_gmail_draft",
    "add_gmail_label",
    "telegram",
    "whatsapp",
    "slack_send_message",
    "linkedin",
}

SECURITY_REVIEW_NODE_TYPES = {
    "webhook_trigger",
    "form_trigger",
    "http_request",
    "file_write",
    "search_update_google_sheets",
    "read_google_sheets",
    "create_google_docs",
    "read_google_docs",
    "update_google_docs",
    "send_gmail_message",
    "create_gmail_draft",
    "add_gmail_label",
    "telegram",
    "whatsapp",
    "slack_send_message",
    "linkedin",
    "ai_agent",
    "code",
}

SECURITY_PII_FIELD_HINTS = (
    "email",
    "phone",
    "mobile",
    "name",
    "first_name",
    "last_name",
    "address",
    "city",
    "state",
    "zip",
    "postal",
    "dob",
    "birth",
    "ssn",
    "aadhaar",
    "pan",
    "customer",
    "user",
    "profile",
)

PUBLISH_CRITICAL_NODE_TYPES = {
    "http_request",
    "ai_agent",
    "search_update_google_sheets",
    "send_gmail_message",
    "create_gmail_draft",
    "add_gmail_label",
    "telegram",
    "whatsapp",
    "slack_send_message",
    "linkedin",
    "file_write",
    "merge",
    "if_else",
    "switch",
}

N8N_NODE_TYPE_EQUIVALENTS: dict[str, str] = {
    "n8n-nodes-base.httpRequest": "http_request",
    "n8n-nodes-base.if": "if_else",
    "n8n-nodes-base.switch": "switch",
    "n8n-nodes-base.merge": "merge",
    "n8n-nodes-base.function": "code",
    "n8n-nodes-base.functionItem": "code",
    "n8n-nodes-base.code": "code",
    "n8n-nodes-base.set": "code",
    "n8n-nodes-base.telegram": "telegram",
    "n8n-nodes-base.gmail": "send_gmail_message",
    "n8n-nodes-base.slack": "slack_send_message",
    "n8n-nodes-base.webhook": "webhook_trigger",
    "n8n-nodes-base.cron": "schedule_trigger",
}

N8N_MIGRATION_KNOWN_UNSUPPORTED = {
    "n8n-nodes-base.splitInBatches",
    "n8n-nodes-base.executeWorkflow",
    "n8n-nodes-base.wait",
}

NODE_TYPE_DETAILS: dict[str, dict[str, Any]] = {
    "manual_trigger": {
        "category": "trigger",
        "description": "Starts a workflow manually. Must have empty config.",
    },
    "form_trigger": {
        "category": "trigger",
        "description": "Starts from a form submission. Include form_title, form_description, and a non-empty fields array.",
        "rules": [
            "Each field object should include name, label, type, and required.",
            "Supported field.type values: text, email, number, textarea, select, radio, checkbox, date, time, datetime, url, phone, rating, checkbox_group.",
            "select, radio, and checkbox_group fields require options: [{label: string, value: string}] with at least one option.",
            "select and radio submit one selected string value; checkbox submits a boolean; checkbox_group submits an array of selected value strings.",
            "date submits YYYY-MM-DD, time submits HH:MM, datetime submits an ISO 8601 string, url submits a URL string, phone submits a phone string, and rating submits an integer from 1 to max_stars.",
            "Optional extras by type: select placeholder; radio layout inline/stacked; checkbox default_checked; date min_date/max_date; time min_time/max_time; datetime min_datetime/max_datetime; phone default_country_code; rating max_stars; checkbox_group options only.",
        ],
    },
    "webhook_trigger": {
        "category": "trigger",
        "description": "Starts from an incoming webhook.",
        "rules": [
            "Use config keys: path and method.",
            "method should be one of GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD.",
        ],
    },
    "schedule_trigger": {
        "category": "trigger",
        "description": "Starts workflow on a recurring schedule.",
        "rules": [
            "Preferred: use config.rules as a non-empty array.",
            "Each rule should have interval in [minutes, hours, days, weeks, months, custom], enabled, and interval-specific fields.",
            "For custom interval, use cron field with a 5-field cron expression.",
            "Legacy fallback also supports config.cron or minute/hour/day_of_month/month/day_of_week.",
            "timezone should be an IANA timezone name (for example Asia/Kolkata or UTC).",
            "enabled can pause/resume schedule execution.",
        ],
    },
    "workflow_trigger": {
        "category": "trigger",
        "description": "Starts a child workflow from another workflow execution context.",
        "rules": [
            "Category: Trigger. Type id: workflow_trigger.",
            "Use config keys: input_data_mode, input_schema, json_example.",
            "input_data_mode must be one of fields, json_example, accept_all.",
            "input_schema is an array of {\"name\": string, \"type\": \"Allow any type\" | \"String\" | \"Number\" | \"Boolean\" | \"Array\" | \"Object\"} and is used when input_data_mode=fields.",
            "json_example is a string and is used when input_data_mode=json_example.",
            "A child workflow must always start with workflow_trigger.",
            "Never place workflow_trigger anywhere except as the first node of a workflow.",
            "Never place more than one workflow_trigger per workflow.",
        ],
    },
    "execute_workflow": {
        "category": "action",
        "description": "Calls a child workflow from a parent workflow.",
        "rules": [
            "Category: Action. Type id: execute_workflow.",
            "Use config keys: source, workflow_id, workflow_json, workflow_inputs, mode.",
            "source must be database or json.",
            "workflow_id is the UUID of the child workflow when source=database.",
            "workflow_json is the raw definition JSONB string when source=json.",
            "workflow_inputs is an array of {\"key\": string, \"value\": string}; values support {{node_id.field}} syntax.",
            "mode must be run_once or run_per_item.",
            "For sub-workflow patterns generated from user intent, use source=database and leave workflow_id as an empty string because the child workflow does not exist yet.",
        ],
    },
    "get_gmail_message": {
        "category": "action",
        "description": "Fetches emails from Gmail API using OAuth credential. Requires credential_id.",
        "rules": [
            "Use config keys: credential_id, folder, query, limit, unread_only, include_body, mark_as_read.",
            "limit should be a small positive integer as a string (for example '10').",
        ],
    },
    "send_gmail_message": {
        "category": "action",
        "description": "Sends email through Gmail API using OAuth credential. Requires credential_id, to, subject, and body.",
        "rules": [
            "Use config keys: credential_id, to, cc, bcc, reply_to, subject, body, image, is_html.",
            "Use comma-separated emails in to/cc/bcc when multiple recipients are needed.",
            "If attaching an Image Gen result, set image to {{image_gen_node_id.image_base64}} or {{image_gen_node_id.image_url}}.",
            "Use Autoflow template syntax {{...}} for dynamic values, not {....}.",
        ],
    },
    "create_gmail_draft": {
        "category": "action",
        "description": "Creates a Gmail draft using OAuth credential. Requires credential_id, to, subject, and body.",
        "rules": [
            "Use config keys: credential_id, to, subject, body.",
            "All fields support Autoflow template syntax {{...}}.",
            "Use this instead of send_gmail_message when the user asks to draft, prepare, or save an email without sending it.",
        ],
    },
    "add_gmail_label": {
        "category": "action",
        "description": "Finds or creates a Gmail label and applies it to a Gmail message. Requires credential_id, message_id, and label_name.",
        "rules": [
            "Use config keys: credential_id, message_id, label_name.",
            "message_id should usually reference an upstream Gmail output, for example {{send_gmail_node.message_id}}.",
            "label_name supports nested Gmail labels using /, for example Autoflow/Processed.",
        ],
    },
    "create_google_sheets": {
        "category": "action",
        "description": "Creates a new Google Spreadsheet using a Sheets credential.",
        "rules": [
            "Use config keys: credential_id, title, sheet_name, columns.",
            "credential_id must point to app_credentials with app_name=sheets.",
            "title is required. sheet_name is optional.",
            "columns is optional and should be an array of header names to write into row 1.",
        ],
    },
    "search_update_google_sheets": {
        "category": "action",
        "description": "Performs Google Sheets operations like append row, delete rows, overwrite row, upsert row, add columns, and delete columns.",
        "rules": [
            "Use config keys: credential_id, spreadsheet_source_type, spreadsheet_id, spreadsheet_url, sheet_name, operation, key_column, key_value, update_mappings, append_columns, append_values, columns_to_add, columns_to_delete, auto_create_headers.",
            "sheet_name should be the worksheet tab title (for example Sheet1), not the spreadsheet document title.",
            "operation should be one of append_row, delete_rows, overwrite_row, upsert_row, add_columns, delete_columns (aliases like append/delete/overwrite/upsert are also accepted).",
            "For overwrite_row/upsert_row use key_column + key_value and update_mappings like [{\"column\": \"Status\", \"value\": \"Processed\"}].",
            "For append_row prefer update_mappings like overwrite/upsert; legacy append_columns + append_values is also supported.",
            "For add_columns and delete_columns use columns_to_add / columns_to_delete arrays.",
            "Legacy fallback update_column + update_value is still supported for backward compatibility.",
            "Column references can be header names, column letters (A/B/C), or column numbers.",
        ],
    },
    "read_google_sheets": {
        "category": "action",
        "description": "Reads rows from a Google Sheets worksheet.",
        "rules": [
            "Use config keys: credential_id, spreadsheet_source_type, spreadsheet_id, spreadsheet_url, sheet_name, range, first_row_as_header, include_empty_rows, max_rows.",
            "spreadsheet_source_type must be id or url. Use sheet_name as the worksheet tab name.",
            "first_row_as_header maps rows to objects; when false, rows are returned as arrays.",
        ],
    },
    "limit": {
        "category": "transform",
        "description": "Keeps only a fixed slice of items from an input array.",
        "rules": [
            "Use config keys: input_key, limit, offset, start_from.",
            "start_from should be start or end.",
            "Set limit=0 to return an empty array safely.",
        ],
    },
    "sort": {
        "category": "transform",
        "description": "Sorts an array of primitives or objects by a field.",
        "rules": [
            "Use config keys: input_key, sort_by, order, data_type, nulls, case_sensitive.",
            "Leave sort_by empty to sort primitive arrays directly.",
            "order should be asc or desc; nulls should be first or last.",
        ],
    },
    "create_google_docs": {
        "category": "action",
        "description": "Creates a Google Doc using a Docs credential.",
        "rules": [
            "Use config keys: credential_id, title, initial_content.",
            "credential_id must point to app_credentials with app_name=docs.",
            "title is required. initial_content is optional.",
        ],
    },
    "read_google_docs": {
        "category": "action",
        "description": "Reads text content from a Google Doc.",
        "rules": [
            "Use config keys: credential_id, document_source_type, document_id, document_url, max_characters, include_raw_json.",
            "document_source_type must be id or url.",
            "When source type is url, document_url is required. Otherwise document_id is required.",
        ],
    },
    "update_google_docs": {
        "category": "action",
        "description": "Updates a Google Doc by appending text or replacing text.",
        "rules": [
            "Use config keys: credential_id, document_id, operation, text, image, match_text, match_case.",
            "operation must be append_text or replace_all_text.",
            "match_text is required when operation is replace_all_text.",
            "If inserting an Image Gen result, set image to {{image_gen_node_id.image_url}}.",
        ],
    },
    "telegram": {
        "category": "action",
        "description": "Sends a Telegram message. Use credential_id and message. The credential stores bot token + chat_id.",
        "rules": [
            "Use config keys: credential_id, message, image, parse_mode.",
            "If sending an Image Gen result, set image to {{image_gen_node_id.image_base64}} or {{image_gen_node_id.image_url}}.",
            "Optional parse_mode can be one of: HTML, Markdown, MarkdownV2.",
            "Use Autoflow template syntax {{...}} for dynamic values, not {....}.",
        ],
    },
    "whatsapp": {
        "category": "action",
        "description": "Sends a WhatsApp template message via the Meta Cloud API.",
        "rules": [
            "Use config keys: credential_id, to_number, template_name, template_params, language_code.",
            "credential_id must point to app_credentials with app_name=whatsapp.",
            "to_number is the recipient phone in E.164 format (e.g. +919876543210).",
            "template_name must be a Meta-approved template (e.g. hello_world).",
            "template_params is an optional list of string values for body placeholders.",
            "language_code defaults to en_US.",
            "Use Autoflow template syntax {{...}} for dynamic values, not {....}.",
        ],
    },
    "linkedin": {
        "category": "action",
        "description": "Posts content to LinkedIn using a connected LinkedIn credential.",
        "rules": [
            "Use config keys: credential_id, post_text, image, visibility.",
            "If attaching an Image Gen result, set image to {{image_gen_node_id.image_base64}} or {{image_gen_node_id.image_url}}.",
            "visibility should be PUBLIC or CONNECTIONS.",
        ],
    },
    "http_request": {
        "category": "input_output",
        "description": "Calls external HTTP APIs with configurable method, headers, query/body, and auth modes.",
        "rules": [
            "Use config keys: url, method, auth_mode, credential_id, headers_json, query_json, body_type, body_json, body_form_json, body_raw.",
            "method should be one of GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD.",
            "auth_mode should be none, bearer, basic, or api_key.",
            "response_format should be auto, json, or text.",
        ],
    },
    "file_read": {
        "category": "input_output",
        "description": "Reads a local file from an allowed directory and returns parsed content.",
        "rules": [
            "Use config keys: file_path, parse_as, encoding, max_bytes, include_metadata, csv_delimiter.",
            "parse_as should be one of auto, text, json, csv, lines, base64.",
            "Allowed file paths/extensions are controlled by FILE_NODE_ALLOWED_BASE_DIRS and FILE_NODE_ALLOWED_EXTENSIONS.",
        ],
    },
    "file_write": {
        "category": "input_output",
        "description": "Writes content to a local file in an allowed directory.",
        "rules": [
            "Use config keys: file_path, content_source, input_key, content_text, input_format, write_mode, encoding, create_dirs.",
            "write_mode should be create, overwrite, or append.",
            "input_format should be auto, text, json, or base64.",
            "Allowed file paths/extensions are controlled by FILE_NODE_ALLOWED_BASE_DIRS and FILE_NODE_ALLOWED_EXTENSIONS.",
        ],
    },
    "slack_send_message": {
        "category": "action",
        "description": "Sends a message through a Slack Incoming Webhook.",
        "rules": [
            "Use config keys: credential_id, message, webhook_url, channel.",
            "credential_id must point to app_credentials with app_name=slack.",
            "message is required and specifies the text to send. Supports {{ }} template expressions.",
            "webhook_url and channel are optional legacy overrides. Preferred source is the credential data.",
        ],
    },
    "if_else": {
        "category": "logic",
        "description": "Conditional branch node. Supports one or more condition rows with AND/OR logic. Output branches are true and false.",
        "rules": [
            "Use the new config shape for all newly generated workflows: condition_type and conditions.",
            "condition_type must be AND or OR.",
            "conditions must contain one or more objects with field, operator, and value. Optional keys: value_mode, value_field, case_sensitive.",
            "For prompts with multiple checks joined by AND, set condition_type=AND. For prompts with alternatives joined by OR, set condition_type=OR.",
            "Do not prefer the legacy single-condition field/operator/value shape for new workflows.",
            f"operator must be one of: {', '.join(SHARED_OPERATORS)}.",
            "Set value_mode=literal to compare against value, or value_mode=field to compare against value_field inside each condition.",
            "case_sensitive applies to equals/not_equals/contains/not_contains and defaults to true.",
            "Example AND config: {\"condition_type\":\"AND\",\"conditions\":[{\"field\":\"status\",\"operator\":\"equals\",\"value\":\"active\"},{\"field\":\"priority\",\"operator\":\"greater_than\",\"value\":5}]}",
            "Example OR config: {\"condition_type\":\"OR\",\"conditions\":[{\"field\":\"country\",\"operator\":\"equals\",\"value\":\"India\"},{\"field\":\"country\",\"operator\":\"equals\",\"value\":\"USA\"}]}",
            "Outgoing edges from this node must use branch values true or false.",
        ],
    },
    "switch": {
        "category": "logic",
        "description": "Multi-branch conditional node using first-match-wins case evaluation.",
        "rules": [
            f"Each case object must include id, label, operator, and value. operator must be one of: {', '.join(SHARED_OPERATORS)}.",
            "Every outgoing edge must set branch equal to one case id or the default_case value.",
        ],
    },
    "merge": {
        "category": "logic",
        "description": "n8n-style merge node for appending, combining, or choosing a specific input.",
        "rules": [
            "Use config keys: mode, input_count, choose_branch, output_key, join_type, input_1_field, input_2_field.",
            "mode must be one of: append, combine, combine_by_position, combine_by_fields, choose_branch.",
            "input_count should match how many merge input handles are connected (minimum 2).",
            "append mode returns an array under output_key (default output_key='merged').",
            "combine mode merges object inputs into one object.",
            "combine_by_position supports join_type inner/left/right/outer.",
            "combine_by_fields requires input_1_field and input_2_field, and supports join_type inner/left/right/outer.",
            "choose_branch forwards the configured input handle (e.g. choose_branch='input3').",
        ],
    },
    "filter": {
        "category": "logic",
        "description": "Filters an array at input_key by comparing field against value.",
        "rules": [
            f"operator must be one of: {', '.join(SHARED_OPERATORS)}.",
        ],
    },
    "delay": {
        "category": "transform",
        "description": "Pauses workflow execution for a configured time, then forwards data unchanged.",
        "rules": [
            "Use config keys: wait_mode, amount, unit, until_datetime, timezone.",
            "wait_mode must be one of after_interval, until_datetime.",
            "Preferred unit values: seconds, minutes, hours, days, months.",
            "For wait_mode=after_interval, provide amount and unit.",
            "For wait_mode=until_datetime, provide until_datetime (ISO) and optional timezone.",
        ],
    },
    "datetime_format": {
        "category": "transform",
        "description": "Parses a date string and overwrites the same field in output.",
    },
    "split_in": {
        "category": "transform",
        "description": "Splits an array into per-item loop iterations. Usually pair with split_out later in the graph.",
    },
    "split_out": {
        "category": "transform",
        "description": "Collects split loop results into one array. Usually paired with split_in.",
    },
    "aggregate": {
        "category": "transform",
        "description": "Aggregates numeric values from an array into one scalar.",
        "rules": [
            "operation must be one of sum, count, min, max, avg.",
            "field is required for sum, min, max, and avg.",
        ],
    },
    "ai_agent": {
        "category": "ai",
        "description": "Runs an LLM task. Use system_prompt and command config keys; optional response_enhancement controls response polishing.",
        "rules": [
            "Prefer pairing every ai_agent with exactly one connected chat model sub-node.",
            "Put the main task instruction in command.",
            "Use system_prompt for role or behavior instructions.",
            "response_enhancement can be auto, always, or off.",
            "Structured AI results are returned under output (for example output.summary, output.sentiment).",
            "When referencing structured AI results downstream, prefer {{output.some_key}}.",
            "When referencing upstream workflow data, use {{path.to.value}} templates.",
            "For form triggers, both {{field_name}} and {{form.field_name}} are supported.",
        ],
    },
    "image_gen": {
        "category": "ai",
        "description": "Generates one image with OpenAI and returns base64 plus a browser-ready data URL for downstream nodes.",
        "rules": [
            "Use this node whenever the user asks to generate, create, make, or include an AI-generated image/visual.",
            "Use config keys: credential_id, model, prompt, size, quality, style.",
            "credential_id should be an empty string unless the user explicitly provided a known credential id.",
            "prompt is required and should be a detailed visual prompt. It may include Autoflow templates from upstream data.",
            "Supported models: gpt-image-1, dall-e-3, dall-e-2.",
            "Valid sizes: dall-e-3 supports 1024x1024, 1792x1024, 1024x1792; dall-e-2 supports 256x256, 512x512, 1024x1024; gpt-image-1 supports 1024x1024, 1536x1024, 1024x1536.",
            "quality should be standard or hd. style should be vivid or natural.",
            "Outputs available to later nodes: image_base64, image_url, mime_type, prompt_used, revised_prompt, width, height, model.",
            "For image-capable downstream nodes, reference {{image_gen_node_id.image_base64}} or {{image_gen_node_id.image_url}} in their image config field.",
        ],
    },
    "chat_model_openai": {
        "category": "ai",
        "description": "OpenAI chat model configuration sub-node for ai_agent.",
        "rules": [
            "Connect this node to an ai_agent with targetHandle set to chat_model.",
            "Use credential_id, model, temperature, and max_tokens only.",
        ],
    },
    "chat_model_groq": {
        "category": "ai",
        "description": "Groq chat model configuration sub-node for ai_agent.",
        "rules": [
            "Connect this node to an ai_agent with targetHandle set to chat_model.",
            "Use credential_id, model, temperature, and max_tokens only.",
        ],
    },
}


class WorkflowGenerationError(ValueError):
    """Raised when the model response cannot be converted into a valid workflow."""


@dataclass(slots=True)
class GeneratedWorkflowResult:
    definition: WorkflowDefinition
    name: str | None = None
    message: str | None = None


class LLMService:
    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        max_retries: int = 1,
    ) -> None:
        self.model = model or os.getenv("OPENAI_WORKFLOW_MODEL") or "gpt-4o-mini"
        self.max_retries = max_retries
        self._api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
        self.client = client
        self.system_prompt = self.build_workflow_generation_system_prompt()

    async def generate_workflow_definition(self, prompt: str) -> GeneratedWorkflowResult:
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise WorkflowGenerationError("Prompt must not be empty.")

        client = self._get_client()
        generation_temperature = self._resolve_generation_temperature()

        initial_user_prompt = self._build_generation_user_prompt(cleaned_prompt)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": initial_user_prompt},
        ]
        last_error: WorkflowGenerationError | None = None

        for _ in range(self.max_retries + 1):
            if isinstance(client, BaseLLMProvider):
                user_prompt = initial_user_prompt
                if last_error is not None:
                    user_prompt = self._build_generation_user_prompt(
                        cleaned_prompt,
                        validation_error=str(last_error),
                    )

                raw_content = await client.complete(
                    system_prompt=self.system_prompt,
                    user_prompt=user_prompt,
                    model=self.model,
                    temperature=generation_temperature,
                    max_tokens=None,
                )
            else:
                chat_kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                }
                if generation_temperature is not None:
                    chat_kwargs["temperature"] = generation_temperature

                response = await client.chat.completions.create(**chat_kwargs)
                raw_content = self._extract_response_text(response)

            try:
                definition, suggested_name, response_message = self.validate_generated_workflow(
                    raw_content,
                    user_prompt=cleaned_prompt,
                    include_response_message=True,
                )
                if not suggested_name:
                    suggested_name = self._derive_workflow_name(cleaned_prompt)
                if self._prompt_implies_sub_workflow(cleaned_prompt):
                    response_message = SUB_WORKFLOW_RESPONSE_MESSAGE
                return GeneratedWorkflowResult(
                    definition=definition,
                    name=suggested_name,
                    message=response_message,
                )
            except WorkflowGenerationError as exc:
                last_error = exc
                if not isinstance(client, BaseLLMProvider):
                    messages.extend(
                        [
                            {"role": "assistant", "content": raw_content},
                            {
                                "role": "user",
                                "content": self._build_generation_user_prompt(
                                    cleaned_prompt,
                                    validation_error=str(exc),
                                ),
                            },
                        ]
                    )

        if self._prompt_implies_sub_workflow(cleaned_prompt):
            return self._build_sub_workflow_parent_fallback(cleaned_prompt)

        raise WorkflowGenerationError(
            "Could not generate a valid workflow from the model response."
        ) from last_error

    async def assist_workflow(
        self,
        *,
        prompt: str,
        interaction_mode: str = "build",
        current_definition: WorkflowDefinition | None = None,
        conversation_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise WorkflowGenerationError("Prompt must not be empty.")

        normalized_interaction_mode = str(interaction_mode or "build").strip().lower()
        if normalized_interaction_mode not in {"build", "ask"}:
            normalized_interaction_mode = "build"

        state = conversation_state or {}
        confirmed_choices = state.get("confirmed_choices")
        existing_assumptions = self._sanitize_string_list(state.get("assumptions"))
        recent_messages = self._sanitize_recent_messages(state.get("recent_messages"))
        last_mode = str(state.get("last_mode") or "").strip().lower() or None
        workflow_context_origin = str(
            state.get("workflow_context_origin") or "accepted_canvas"
        ).strip().lower()
        if workflow_context_origin not in {"accepted_canvas", "preview", "unknown"}:
            workflow_context_origin = "unknown"
        preview_active = bool(state.get("preview_active", False))
        last_referenced_nodes = self._sanitize_node_reference_list(
            state.get("last_referenced_nodes")
        )
        last_unresolved_question = self._sanitize_single_line(
            state.get("last_unresolved_question"),
            max_chars=320,
        )
        last_accepted_workflow_signature = self._sanitize_single_line(
            state.get("last_accepted_workflow_signature"),
            max_chars=220,
        )

        prompt_with_choices = self._merge_confirmed_choices_into_prompt(
            cleaned_prompt,
            confirmed_choices=confirmed_choices,
        )
        direct_question_prompt = prompt_with_choices
        prompt_with_choices = self._append_recent_chat_context_to_prompt(
            prompt_with_choices,
            recent_messages=recent_messages,
        )
        prompt_with_choices = self._append_memory_anchors_to_prompt(
            prompt_with_choices,
            last_referenced_nodes=last_referenced_nodes,
            last_unresolved_question=last_unresolved_question,
            last_accepted_workflow_signature=last_accepted_workflow_signature,
        )
        if normalized_interaction_mode == "ask":
            assistant_message = await self._answer_autoflow_question(
                prompt_with_choices,
                current_definition=current_definition,
                question_text=direct_question_prompt,
                recent_messages=recent_messages,
                workflow_context_origin=workflow_context_origin,
                preview_active=preview_active,
                last_referenced_nodes=last_referenced_nodes,
                last_unresolved_question=last_unresolved_question,
                last_accepted_workflow_signature=last_accepted_workflow_signature,
            )
            return {
                "mode": "ask",
                "assistant_message": assistant_message,
                "questions": [],
                "assumptions": existing_assumptions,
                "definition": None,
                "name": None,
                "change_summary": None,
            }

        is_modify_mode = (
            current_definition is not None
            and (
                self._prompt_requests_modify(prompt_with_choices)
                or last_mode == "modify"
            )
        )
        analysis = self._analyze_prompt_for_assistant(prompt_with_choices)
        missing_logic_slots = analysis["missing_logic_slots"]
        needs_clarification = bool(analysis.get("needs_clarification"))
        assumptions = self._dedupe_non_empty_strings(
            [*existing_assumptions, *analysis["assumptions"]]
        )
        questions = self._build_clarify_questions(
            missing_logic_slots,
            prompt=prompt_with_choices,
            analysis=analysis,
        )

        if needs_clarification and not is_modify_mode:
            if not questions:
                questions = self._build_clarify_questions(
                    ["trigger_type"],
                    prompt=prompt_with_choices,
                    analysis=analysis,
                )
            message_lines = [
                "I need a couple of workflow details before generating an accurate flow.",
            ]
            for idx, question in enumerate(questions, start=1):
                message_lines.append(f"{idx}. {question['question']}")
            return {
                "mode": "clarify",
                "assistant_message": "\n".join(message_lines),
                "questions": questions[:2],
                "assumptions": assumptions,
                "definition": None,
                "name": None,
                "change_summary": None,
            }

        generation_prompt = prompt_with_choices
        generation_prompt = self._append_inferred_intent_to_prompt(
            generation_prompt,
            analysis=analysis,
        )
        if assumptions:
            generation_prompt = self._append_assumptions_to_prompt(
                generation_prompt,
                assumptions=assumptions,
            )
        if is_modify_mode and current_definition is not None:
            generation_prompt = self._build_modify_generation_prompt(
                prompt=generation_prompt,
                current_definition=current_definition,
            )

        generated = await self.generate_workflow_definition(generation_prompt)
        safe_definition = self._strip_sensitive_config_values(generated.definition)

        mode = "modify" if is_modify_mode else "generate"
        if (
            mode == "modify"
            and current_definition is not None
            and not self._modify_prompt_allows_full_rebuild(prompt_with_choices)
            and self._is_broad_modify_change(
                previous_definition=current_definition,
                updated_definition=safe_definition,
            )
        ):
            strict_modify_prompt = self._build_pinpoint_modify_generation_prompt(
                prompt=generation_prompt,
                current_definition=current_definition,
            )
            retried = await self.generate_workflow_definition(strict_modify_prompt)
            safe_definition = self._strip_sensitive_config_values(retried.definition)
            if retried.name:
                generated = GeneratedWorkflowResult(
                    definition=safe_definition,
                    name=retried.name,
                )

        summary = self._build_generation_summary(
            definition=safe_definition,
            mode=mode,
            assumptions=assumptions,
        )
        if generated.message:
            summary = generated.message

        change_summary = None
        if mode == "modify" and current_definition is not None:
            change_summary = self._summarize_definition_changes(
                previous_definition=current_definition,
                updated_definition=safe_definition,
            )
        returned_name = generated.name if mode != "modify" else None

        return {
            "mode": mode,
            "assistant_message": summary,
            "questions": [],
            "assumptions": assumptions,
            "definition": safe_definition,
            "name": returned_name,
            "change_summary": change_summary,
        }

    @classmethod
    def _analyze_prompt_for_assistant(cls, prompt: str) -> dict[str, Any]:
        lowered = prompt.lower()
        prompt_word_count = len(re.findall(r"\b\w+\b", lowered))
        sub_workflow_requested = cls._prompt_implies_sub_workflow(prompt)

        inferred_trigger = cls._infer_trigger_type_from_prompt(prompt)
        if sub_workflow_requested and inferred_trigger == "workflow_trigger":
            inferred_trigger = None
        event_language_present = any(token in lowered for token in EVENT_LANGUAGE_HINTS)
        trigger_known = inferred_trigger is not None
        action_known = any(token in lowered for token in ASSISTANT_ACTION_HINTS)
        requested_channels = cls._infer_requested_channel_node_types(lowered)
        channel_requested = bool(requested_channels) or any(
            token in lowered for token in ("send", "post", "notify", "message", "email")
        )
        channel_known = any(
            token in lowered
            for tokens in ASSISTANT_CHANNEL_HINTS.values()
            for token in tokens
        )
        branching_requested = any(token in lowered for token in ASSISTANT_BRANCH_HINTS)
        branch_condition_known = any(
            token in lowered
            for token in (" equals ", " contains ", " greater", " less", "status", "priority")
        )
        timing_requested = any(token in lowered for token in ASSISTANT_TIMING_HINTS)
        timing_known = (
            cls._extract_schedule_rule_from_prompt(prompt) is not None
            or bool(SEQUENCE_DAYS_PATTERN.search(lowered))
            or bool(ASSISTANT_TIMING_VALUE_PATTERN.search(lowered))
        )
        data_mapping_known = any(token in lowered for token in ASSISTANT_DATA_MAPPING_HINTS)
        multi_channel_requested = len(requested_channels) >= 2
        image_requested = cls._prompt_requests_image_generation(lowered)
        default_trigger = cls._infer_default_trigger_from_prompt(
            prompt=prompt,
            inferred_trigger=inferred_trigger,
        )
        has_actionable_signal = (
            action_known
            or channel_known
            or timing_known
            or branching_requested
            or image_requested
            or sub_workflow_requested
            or bool(requested_channels)
        )

        missing_logic_slots: list[str] = []
        assumptions: list[str] = []

        if not trigger_known:
            if default_trigger and default_trigger != "manual_trigger":
                assumptions.append(
                    f"Start trigger inferred as {default_trigger} from your prompt context."
                )
            elif has_actionable_signal and event_language_present:
                assumptions.append("Event-style intent detected; using webhook_trigger by default.")
            else:
                missing_logic_slots.append("trigger_type")
                assumptions.append(
                    "Default trigger can be manual_trigger only when the request is truly on-demand/test."
                )

        if not action_known:
            missing_logic_slots.append("primary_action")
            if has_actionable_signal:
                assumptions.append(
                    "Primary action inferred from your context and channel intent."
                )
        if sub_workflow_requested:
            assumptions.append(
                "Sub-workflow intent detected; generating only the parent workflow with execute_workflow."
            )

        if channel_requested and not channel_known:
            missing_logic_slots.append("destination_channel")
            assumptions.append(
                "Destination channel will default to slack_send_message when not explicitly recognized."
            )

        if branching_requested and not branch_condition_known:
            missing_logic_slots.append("branch_condition")
            assumptions.append("Single-path flow is used when branch conditions are not provided.")

        if timing_requested and not timing_known:
            missing_logic_slots.append("timing")
            assumptions.append("Default schedule cadence can be daily when timing is unspecified.")

        if not data_mapping_known:
            assumptions.append("Dynamic fields use safe placeholders like {{email}} and {{message}}.")

        complexity_level = cls._classify_prompt_complexity(
            prompt=prompt,
            requested_channels=requested_channels,
            branching_requested=branching_requested,
            timing_requested=timing_requested,
        )

        questions = cls._build_clarify_questions(missing_logic_slots)
        needs_clarification = not has_actionable_signal and prompt_word_count <= 6
        return {
            "needs_clarification": needs_clarification,
            "missing_logic_slots": missing_logic_slots,
            "questions": questions[:2],
            "assumptions": assumptions,
            "signals": {
                "trigger_known": trigger_known,
                "action_known": action_known,
                "channel_known": channel_known,
                "channel_requested": channel_requested,
                "branching_requested": branching_requested,
                "branch_condition_known": branch_condition_known,
                "timing_requested": timing_requested,
                "timing_known": timing_known,
                "data_mapping_known": data_mapping_known,
                "multi_channel_requested": multi_channel_requested,
                "requested_channels": sorted(requested_channels),
                "image_requested": image_requested,
                "sub_workflow_requested": sub_workflow_requested,
                "has_actionable_signal": has_actionable_signal,
                "inferred_trigger": inferred_trigger,
                "default_trigger": default_trigger,
                "event_language_present": event_language_present,
                "complexity_level": complexity_level,
            },
        }

    @classmethod
    def _append_inferred_intent_to_prompt(
        cls,
        prompt: str,
        *,
        analysis: Mapping[str, Any],
    ) -> str:
        signals = analysis.get("signals") if isinstance(analysis, Mapping) else {}
        if not isinstance(signals, Mapping):
            return prompt

        inferred_lines: list[str] = []
        requested_channels = [
            str(item).strip()
            for item in (signals.get("requested_channels") or [])
            if str(item).strip()
        ]
        inferred_trigger = str(signals.get("inferred_trigger") or "").strip()
        default_trigger = str(signals.get("default_trigger") or "").strip()
        complexity_level = str(signals.get("complexity_level") or "").strip()
        if requested_channels:
            rendered_channels = ", ".join(
                CHANNEL_DISPLAY_NAMES.get(channel, channel)
                for channel in requested_channels
            )
            inferred_lines.append(f"Use these requested channels: {rendered_channels}.")

        if bool(signals.get("sub_workflow_requested")):
            inferred_lines.append(
                "Generate only the parent workflow. Include execute_workflow with source=database and workflow_id=\"\". Do not include workflow_trigger in this parent workflow."
            )

        if inferred_trigger:
            inferred_lines.append(f"Use {inferred_trigger} as the start trigger.")
        elif default_trigger and default_trigger != "manual_trigger":
            inferred_lines.append(
                f"If trigger type is not explicit, use {default_trigger} based on user intent."
            )
        elif not bool(signals.get("trigger_known")):
            inferred_lines.append(
                "Use manual_trigger only if no event-based or schedule-based trigger is implied."
            )

        if bool(signals.get("timing_known")) and bool(signals.get("multi_channel_requested")):
            inferred_lines.append(
                "Treat this as a multi-step nurture/outreach flow and keep cadence aligned to requested timeline."
            )

        if complexity_level == "simple":
            inferred_lines.append(
                "Keep the workflow concise: only include nodes that are necessary to satisfy the request."
            )
        elif complexity_level == "complex":
            inferred_lines.append(
                "This is a complex request: include required routing/timing nodes, but avoid redundant steps."
            )

        if not inferred_lines:
            return prompt

        return (
            f"{prompt}\n\nInferred execution intent:\n"
            + "\n".join(f"- {line}" for line in inferred_lines)
            + "\nGenerate directly using these inferences unless they conflict with explicit user text."
        )

    @classmethod
    def _build_clarify_questions(
        cls,
        missing_slots: list[str],
        *,
        prompt: str = "",
        analysis: Mapping[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        lowered_prompt = prompt.lower()
        signals = analysis.get("signals") if isinstance(analysis, Mapping) else {}
        if not isinstance(signals, Mapping):
            signals = {}
        requested_channels = [
            str(item).strip()
            for item in (signals.get("requested_channels") or [])
            if str(item).strip()
        ]
        rendered_channels = ", ".join(
            CHANNEL_DISPLAY_NAMES.get(item, item)
            for item in requested_channels
        )
        inferred_trigger = cls._infer_trigger_type_from_prompt(prompt)
        default_trigger = cls._infer_default_trigger_from_prompt(
            prompt=prompt,
            inferred_trigger=inferred_trigger,
        )

        question_map: dict[str, tuple[str, str]] = {
            "trigger_type": (
                "trigger_type",
                (
                    f"I can start this with `{inferred_trigger}` based on your prompt. "
                    "Should I use that trigger, or switch to manual/webhook/form/schedule?"
                    if inferred_trigger
                    else (
                        f"I can infer `{default_trigger}` as a good default start trigger. "
                        "Should I use that, or switch to manual/webhook/form/schedule?"
                        if default_trigger and default_trigger != "manual_trigger"
                        else "How should this workflow start: manual, webhook, form, or schedule?"
                    )
                ),
            ),
            "primary_action": (
                "primary_action",
                "What is the main action this workflow must complete?",
            ),
            "destination_channel": (
                "destination_channel",
                (
                    f"Should I deliver through these channels only: {rendered_channels}, "
                    "or include another destination?"
                    if rendered_channels
                    else "Which destination channel should be used (for example Gmail, Slack, Telegram, or WhatsApp)?"
                ),
            ),
            "branch_condition": (
                "branch_condition",
                "What exact condition should decide each branch path?",
            ),
            "timing": (
                "timing",
                (
                    "What exact cadence should I use (for example every 15 minutes, daily at 9:00, or cron)?"
                    if ("schedule" in lowered_prompt or "sequence" in lowered_prompt or "every " in lowered_prompt)
                    else "What timing should we use (for example every day, every hour, or cron)?"
                ),
            ),
        }
        reason_map: dict[str, str] = {
            "trigger_type": "Needed to choose the start trigger node.",
            "primary_action": "Needed to decide the core action path.",
            "destination_channel": "Needed to select the correct integration nodes.",
            "branch_condition": "Needed to wire if_else/switch branches correctly.",
            "timing": "Needed to configure schedule or delay nodes accurately.",
        }

        questions: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for slot in missing_slots:
            mapped = question_map.get(slot)
            if not mapped:
                continue
            question_id, question = mapped
            if question_id in seen_ids:
                continue
            seen_ids.add(question_id)
            questions.append(
                {
                    "id": question_id,
                    "question": question,
                    "reason": reason_map.get(slot, "Needed to build the workflow accurately."),
                }
            )
        return questions

    @classmethod
    def _infer_default_trigger_from_prompt(
        cls,
        *,
        prompt: str,
        inferred_trigger: str | None = None,
    ) -> str:
        if inferred_trigger:
            return inferred_trigger

        lowered = prompt.lower()
        has_event_language = any(token in lowered for token in EVENT_LANGUAGE_HINTS)
        has_form_intent = any(token in lowered for token in FORM_INTENT_HINTS)
        has_webhook_source = any(token in lowered for token in WEBHOOK_SOURCE_HINTS)
        has_schedule_cadence = cls._extract_schedule_rule_from_prompt(prompt) is not None
        has_sequence_window = bool(SEQUENCE_DAYS_PATTERN.search(lowered)) or any(
            token in lowered for token in ("sequence", "follow-up", "follow up", "nurture", "campaign")
        )

        if has_schedule_cadence:
            return "schedule_trigger"
        if has_sequence_window and has_form_intent:
            return "form_trigger"
        if has_sequence_window and has_webhook_source:
            return "webhook_trigger"
        if has_sequence_window:
            return "schedule_trigger"
        if has_event_language and has_form_intent:
            return "form_trigger"
        if has_event_language and (has_webhook_source or any(token in lowered for token in ASSISTANT_ACTION_HINTS)):
            return "webhook_trigger"
        if has_form_intent and "form" in lowered:
            return "form_trigger"
        if has_webhook_source and has_event_language:
            return "webhook_trigger"
        return "manual_trigger"

    @classmethod
    def _classify_prompt_complexity(
        cls,
        *,
        prompt: str,
        requested_channels: set[str],
        branching_requested: bool,
        timing_requested: bool,
    ) -> str:
        lowered = prompt.lower()
        score = 0
        if len(requested_channels) >= 2:
            score += 2
        elif len(requested_channels) == 1:
            score += 1
        if branching_requested:
            score += 2
        if timing_requested or cls._extract_schedule_rule_from_prompt(prompt) is not None:
            score += 1
        if "sequence" in lowered or "nurture" in lowered or "campaign" in lowered:
            score += 1
        if len(re.findall(r"\b\w+\b", lowered)) >= 28:
            score += 1

        if score >= 4:
            return "complex"
        if score >= 2:
            return "moderate"
        return "simple"

    @classmethod
    def _build_modify_generation_prompt(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition,
    ) -> str:
        summary = cls._build_definition_summary(current_definition)
        baseline_json = json.dumps(current_definition.model_dump(mode="python"), ensure_ascii=True)
        return dedent(
            f"""
            User modification request:
            {prompt}

            Existing workflow summary:
            {summary}

            Existing workflow JSON (authoritative baseline):
            {baseline_json}

            Modification rules:
            - Preserve existing workflow intent unless the user explicitly asks to replace it.
            - Apply only the requested logical changes.
            - Keep unchanged node ids, edge ids, and wiring intact unless the user explicitly asks to alter them.
            - Prefer minimal diff edits over regeneration.
            - Keep credential fields empty; user will configure credentials manually.
            """
        ).strip()

    @classmethod
    def _build_pinpoint_modify_generation_prompt(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition,
    ) -> str:
        baseline_json = json.dumps(current_definition.model_dump(mode="python"), ensure_ascii=True)
        return dedent(
            f"""
            Refine this workflow with pinpoint edits only.

            Requested change:
            {prompt}

            Baseline workflow JSON (must remain mostly unchanged):
            {baseline_json}

            Hard constraints:
            - Preserve all existing nodes and edges unless explicitly required by the requested change.
            - Do not rename node ids or edge ids unless unavoidable.
            - Keep unaffected node configs exactly as-is.
            - Make the smallest possible structural diff.
            - Keep credential fields empty strings.
            - Return only valid workflow JSON.
            """
        ).strip()

    @staticmethod
    def _build_definition_summary(definition: WorkflowDefinition) -> str:
        node_entries = [
            f"{node.id}:{node.type}"
            for node in definition.nodes[:25]
        ]
        edge_entries = [
            f"{edge.source}->{edge.target}"
            for edge in definition.edges[:30]
        ]
        return (
            f"nodes({len(definition.nodes)}): {', '.join(node_entries) or 'none'}; "
            f"edges({len(definition.edges)}): {', '.join(edge_entries) or 'none'}"
        )

    @staticmethod
    def _append_assumptions_to_prompt(prompt: str, *, assumptions: list[str]) -> str:
        rendered_assumptions = "\n".join(f"- {item}" for item in assumptions if item)
        if not rendered_assumptions:
            return prompt
        return (
            f"{prompt}\n\nAssumptions to apply while generating:\n"
            f"{rendered_assumptions}\n"
            "Do not ask about credentials; keep credential fields empty strings."
        )

    @staticmethod
    def _merge_confirmed_choices_into_prompt(
        prompt: str,
        *,
        confirmed_choices: Any,
    ) -> str:
        if not isinstance(confirmed_choices, Mapping) or not confirmed_choices:
            return prompt
        lines: list[str] = []
        for key, value in confirmed_choices.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                continue
            normalized_value = " ".join(str(value).split()).strip()
            if not normalized_value:
                continue
            lines.append(f"- {normalized_key}: {normalized_value}")
        if not lines:
            return prompt
        return f"{prompt}\n\nConfirmed user choices:\n" + "\n".join(lines)

    @staticmethod
    def _prompt_requests_modify(prompt: str) -> bool:
        lowered = prompt.lower()
        return any(token in lowered for token in ASSISTANT_MODIFY_HINTS)

    @classmethod
    def _build_generation_summary(
        cls,
        *,
        definition: WorkflowDefinition,
        mode: str,
        assumptions: list[str],
    ) -> str:
        node_count = len(definition.nodes)
        edge_count = len(definition.edges)
        trigger = next(
            (node.type for node in definition.nodes if node.type in TRIGGER_NODE_TYPES),
            "manual_trigger",
        )
        action_nodes = [
            node.type
            for node in definition.nodes
            if node.type not in TRIGGER_NODE_TYPES
        ][:4]
        rendered_actions = ", ".join(action_nodes) if action_nodes else "no downstream actions"

        if mode == "modify":
            base = "Updated your workflow with the requested changes."
        else:
            base = "Generated a workflow aligned to your request."

        summary_parts = [
            base,
            f"Structure: {node_count} nodes, {edge_count} edges.",
            f"Trigger: `{trigger}`.",
            f"Main steps: {rendered_actions}.",
        ]
        if assumptions:
            summary_parts.append("Applied safe assumptions only where details were missing.")
        return " ".join(summary_parts)

    @classmethod
    def _build_ask_system_prompt(cls) -> str:
        node_reference: list[str] = []
        for node_type in sorted(NODE_CONFIG_DEFAULTS):
            details = NODE_TYPE_DETAILS.get(node_type, {})
            description = str(details.get("description") or "").strip()
            config_schema = NODE_CONFIG_DEFAULTS.get(node_type) or {}
            config_keys = (
                ", ".join(sorted(config_schema.keys()))
                if isinstance(config_schema, Mapping)
                else ""
            )
            rules = details.get("rules") or []
            notable_rules = "; ".join(str(rule).strip() for rule in rules[:2] if str(rule).strip())
            parts = [f"- {node_type}"]
            if description:
                parts.append(description)
            if config_keys:
                parts.append(f"config keys: {config_keys}")
            if notable_rules:
                parts.append(f"notes: {notable_rules}")
            node_reference.append(" | ".join(parts))

        return dedent(
            f"""
            You are the Autoflow product expert assistant in ASK mode.

            Your job in ASK mode:
            - Answer questions about Autoflow features, nodes, parameters, triggers, edges, and best practices.
            - Explain what each parameter does and when to use it.
            - Help users choose practical node combinations for their use case.
            - If users ask "how to build X", provide a concise step-by-step plan with suggested nodes and why.
            - For implementation questions, answer in this structure: Where to place it, Implementation Steps, Parameters.
            - If users ask about if_else or switch routing, include concrete config examples and branch wiring.
            - If users share a runtime error, diagnose the likely root cause first, then provide direct node-level fix steps and a short validation checklist.
            - Avoid repeating the same generic brief when the user asks a specific follow-up.
            - Do not use markdown bold markers like * or ** in your response.
            - Always answer the latest user question first. Do not let older context override the current question intent.
            - If the question is about one node (for example http_request), focus on that node only and explain exactly what to send and where.
            - Ask mode must support all node types for create/edit/add/delete/debug guidance, not only a single node family.
            - Do NOT generate workflow JSON in ASK mode unless user explicitly asks for JSON.
            - Keep guidance concrete and actionable.
            - If uncertain, say what is uncertain instead of inventing facts.

            Important Autoflow conventions:
            - Use double-brace templates for dynamic values, like {{{{email}}}}.
            - For ai_agent structured fields, use {{{{output.field_name}}}} (example: {{{{output.summary}}}}).
            - chat_model_openai/chat_model_groq connect to ai_agent with targetHandle "chat_model".
            - Keep credentials as user-provided values; do not invent secrets.

            Supported nodes quick reference:
            {chr(10).join(node_reference)}
            """
        ).strip()

    @classmethod
    def _build_ask_user_prompt(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        context_pack: str,
    ) -> str:
        workflow_summary = (
            cls._build_definition_summary(current_definition)
            if current_definition is not None
            else "No workflow JSON is currently attached."
        )
        return (
            f"User question:\n{prompt}\n\n"
            f"Current workflow summary:\n{workflow_summary}\n\n"
            f"Context pack:\n{context_pack}\n\n"
            "Answer specifically in context of this current workflow where relevant. "
            "If context is insufficient, say exactly what is missing in 1-2 bullets."
        )

    async def _answer_autoflow_question(
        self,
        prompt: str,
        *,
        current_definition: WorkflowDefinition | None = None,
        question_text: str | None = None,
        recent_messages: list[dict[str, str]] | None = None,
        workflow_context_origin: str = "accepted_canvas",
        preview_active: bool = False,
        last_referenced_nodes: list[str] | None = None,
        last_unresolved_question: str | None = None,
        last_accepted_workflow_signature: str | None = None,
    ) -> str:
        cleaned_prompt = str(prompt or "").strip()
        if not cleaned_prompt:
            return "Please share your Autoflow question, and I can guide you step-by-step."
        latest_question = self._extract_latest_user_question(
            str(question_text or cleaned_prompt)
        )
        ask_context_pack = self._build_ask_context_pack(
            question=latest_question,
            current_definition=current_definition,
            recent_messages=recent_messages or [],
            workflow_context_origin=workflow_context_origin,
            preview_active=preview_active,
            last_referenced_nodes=last_referenced_nodes or [],
            last_unresolved_question=last_unresolved_question or "",
            last_accepted_workflow_signature=last_accepted_workflow_signature or "",
        )

        local_fallback = self._build_local_ask_response(
            prompt=latest_question,
            current_definition=current_definition,
            context_pack=ask_context_pack,
        )

        try:
            client = self._get_client()
            system_prompt = self._build_ask_system_prompt()
            ask_temperature = self._default_temperature_for_model(self.model)
            user_prompt = self._build_ask_user_prompt(
                prompt=latest_question,
                current_definition=current_definition,
                context_pack=ask_context_pack,
            )

            if isinstance(client, BaseLLMProvider):
                answer = await client.complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=self.model,
                    temperature=ask_temperature,
                    max_tokens=900,
                )
                normalized_answer = str(answer or "").strip()
                if normalized_answer:
                    sanitized_answer = self._sanitize_ask_response_format(normalized_answer)
                    if self._is_low_quality_ask_response(
                        answer=sanitized_answer,
                        question=latest_question,
                        current_definition=current_definition,
                    ):
                        return local_fallback
                    return self._clip_assistant_message(sanitized_answer)
                return local_fallback

            chat_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 900,
            }
            if ask_temperature is not None:
                chat_kwargs["temperature"] = ask_temperature

            response = await client.chat.completions.create(**chat_kwargs)
            normalized_answer = self._extract_response_text(response).strip()
            if normalized_answer:
                sanitized_answer = self._sanitize_ask_response_format(normalized_answer)
                if self._is_low_quality_ask_response(
                    answer=sanitized_answer,
                    question=latest_question,
                    current_definition=current_definition,
                ):
                    return local_fallback
                return self._clip_assistant_message(sanitized_answer)
        except Exception:
            return local_fallback
        return local_fallback

    @staticmethod
    def _extract_latest_user_question(raw_text: str) -> str:
        text = " ".join(str(raw_text or "").split()).strip()
        if not text:
            return ""
        # Fast path: regular single-turn prompts.
        if "\n" not in str(raw_text or ""):
            return text

        lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
        if not lines:
            return text

        ignored_prefixes = (
            "workflow brief:",
            "suggested upgrades:",
            "assumptions applied",
            "direct answer:",
            "implementation steps:",
            "branch wiring:",
            "where to place it:",
            "http node overview:",
            "what you have to send:",
            "where to send:",
            "node:",
            "copy",
        )
        intent_tokens = (
            "how",
            "what",
            "why",
            "give",
            "suggest",
            "improve",
            "create",
            "build",
            "steps",
            "sequence",
            "format",
            "prompt",
            "node",
        )
        error_markers = (
            "error",
            "failed",
            "exception",
            "timeout",
            "timed out",
            "not found",
            "bad gateway",
            "status code",
            "404",
            "401",
            "403",
            "422",
            "429",
            "500",
            "502",
            "503",
            "504",
        )

        def _is_timestamp(value: str) -> bool:
            return bool(re.match(r"^\d{1,2}:\d{2}\s*(am|pm)$", value.strip(), flags=re.IGNORECASE))

        def _has_error_marker(value: str) -> bool:
            lowered_value = str(value or "").lower()
            return any(marker in lowered_value for marker in error_markers)

        candidate: str | None = None
        latest_error_line: str | None = None
        for line in reversed(lines):
            lowered = line.lower()
            if not lowered:
                continue
            if latest_error_line is None and _has_error_marker(lowered):
                latest_error_line = " ".join(line.split()).strip()[:260]
            if _is_timestamp(lowered):
                continue
            if any(lowered.startswith(prefix) for prefix in ignored_prefixes):
                continue
            if lowered.startswith("- ") and "?" not in lowered:
                continue
            if re.match(r"^\d+\.\s+", lowered):
                continue
            if any(token in lowered for token in intent_tokens) or "?" in lowered:
                candidate = line
                break
            if candidate is None:
                candidate = line

        final_question = " ".join((candidate or lines[-1]).split()).strip()
        if (
            (not latest_error_line or latest_error_line.lower() == final_question.lower())
            and lines
        ):
            for raw_line in reversed(lines):
                compact_line = " ".join(raw_line.split()).strip()
                if not compact_line or compact_line.lower() == final_question.lower():
                    continue
                if _has_error_marker(compact_line):
                    latest_error_line = compact_line[:260]
                    break
        if (
            latest_error_line
            and final_question
            and latest_error_line.lower() not in final_question.lower()
            and not re.search(r"\b(?:4\d{2}|5\d{2})\b", final_question)
        ):
            final_question = f"{final_question} Error context: {latest_error_line}"
        return final_question[:800]

    @staticmethod
    def _compact_json(value: Any, *, max_chars: int = 260) -> str:
        try:
            rendered = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        except Exception:
            rendered = str(value)
        rendered = " ".join(str(rendered).split())
        if len(rendered) <= max_chars:
            return rendered
        return rendered[: max_chars - 3].rstrip() + "..."

    @classmethod
    def _build_ask_context_pack(
        cls,
        *,
        question: str,
        current_definition: WorkflowDefinition | None,
        recent_messages: list[dict[str, str]],
        workflow_context_origin: str = "accepted_canvas",
        preview_active: bool = False,
        last_referenced_nodes: list[str] | None = None,
        last_unresolved_question: str = "",
        last_accepted_workflow_signature: str = "",
    ) -> str:
        ask_intent = cls._classify_ask_intent(question)
        lines: list[str] = [
            "Question intent:",
            f"- {question}",
            f"- inferred_intent={ask_intent}",
            f"- workflow_context_origin={workflow_context_origin}",
            f"- preview_active={'true' if preview_active else 'false'}",
            "- context_policy=prefer accepted canvas unless user explicitly asks preview details.",
        ]

        if last_referenced_nodes:
            lines.append(
                f"- memory_last_referenced_nodes={', '.join(last_referenced_nodes[:5])}"
            )
        if last_unresolved_question:
            lines.append(f"- memory_last_unresolved_question={last_unresolved_question}")
        if last_accepted_workflow_signature:
            lines.append(
                f"- memory_last_accepted_workflow_signature={last_accepted_workflow_signature[:120]}"
            )

        if recent_messages:
            lines.append("Recent chat memory:")
            for item in recent_messages[-4:]:
                role = str(item.get("role") or "").strip().lower() or "user"
                content = " ".join(str(item.get("content") or "").split()).strip()
                if not content:
                    continue
                lines.append(f"- {role}: {content[:220]}")

        if current_definition is None:
            lines.append("Workflow context: unavailable in this request.")
            return "\n".join(lines)

        nodes_by_id = {node.id: node for node in current_definition.nodes}
        trigger_nodes = [
            f"{node.label} ({node.id})"
            for node in current_definition.nodes
            if node.type in TRIGGER_NODE_TYPES
        ]
        lines.append("Workflow snapshot:")
        lines.append(
            f"- nodes={len(current_definition.nodes)}, edges={len(current_definition.edges)}"
        )
        lines.append(
            f"- triggers={', '.join(trigger_nodes) if trigger_nodes else 'none'}"
        )

        lowered_question = question.lower()
        node_focuses = cls._resolve_node_focuses_from_prompt(
            lowered_question,
            current_definition=current_definition,
        )
        node_focus = node_focuses[0] if node_focuses else None
        if node_focuses:
            lines.append(
                f"- inferred_focus_node_types={', '.join(node_focuses[:3])}"
            )

        matched_nodes: list[Any] = []
        if node_focuses:
            matched_nodes = [
                node for node in current_definition.nodes if node.type in set(node_focuses[:3])
            ][:4]
        if not matched_nodes:
            for node in current_definition.nodes:
                node_id = str(node.id or "").strip().lower()
                node_label = str(node.label or "").strip().lower()
                if node_id and f" {node_id} " in f" {lowered_question} ":
                    matched_nodes.append(node)
                elif node_label and f" {node_label} " in f" {lowered_question} ":
                    matched_nodes.append(node)
                if len(matched_nodes) >= 3:
                    break

        if matched_nodes:
            lines.append("Focused node context:")
            for node in matched_nodes:
                config = node.config if isinstance(node.config, Mapping) else {}
                non_empty_config = {
                    key: value
                    for key, value in config.items()
                    if value not in ("", None, [], {}, False)
                }
                if not non_empty_config and isinstance(config, Mapping):
                    non_empty_config = dict(list(config.items())[:4])

                incoming_edges = [
                    edge for edge in current_definition.edges if edge.target == node.id
                ][:3]
                outgoing_edges = [
                    edge for edge in current_definition.edges if edge.source == node.id
                ][:3]

                lines.append(f"- {node.label} ({node.id}) type={node.type}")
                lines.append(
                    f"  config={cls._compact_json(non_empty_config or {})}"
                )
                if incoming_edges:
                    incoming_refs = []
                    for edge in incoming_edges:
                        source = nodes_by_id.get(edge.source)
                        source_label = source.label if source is not None else edge.source
                        incoming_refs.append(f"{source_label}->{node.id}")
                    lines.append(f"  incoming={', '.join(incoming_refs)}")
                if outgoing_edges:
                    outgoing_refs = []
                    for edge in outgoing_edges:
                        target = nodes_by_id.get(edge.target)
                        target_label = target.label if target is not None else edge.target
                        outgoing_refs.append(f"{node.id}->{target_label}")
                    lines.append(f"  outgoing={', '.join(outgoing_refs)}")
        else:
            primary_nodes = [
                node
                for node in current_definition.nodes
                if node.type not in TRIGGER_NODE_TYPES and node.type not in AI_CHAT_MODEL_NODE_TYPES
            ][:6]
            if primary_nodes:
                lines.append("Primary flow nodes:")
                for node in primary_nodes:
                    lines.append(f"- {node.label} ({node.id}) type={node.type}")

        return "\n".join(lines)

    @staticmethod
    def _clip_assistant_message(message: str, *, max_chars: int = 3900) -> str:
        normalized = str(message or "").strip()
        if not normalized:
            return "I can help with Autoflow workflows, nodes, parameters, and best practices."
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 3].rstrip() + "..."

    @staticmethod
    def _sanitize_ask_response_format(message: str) -> str:
        normalized = str(message or "").strip()
        if not normalized:
            return normalized
        normalized = re.sub(r"\*\*(.*?)\*\*", r"\1", normalized)
        normalized = re.sub(r"(?m)^\s*\*\s+", "- ", normalized)
        return normalized

    @classmethod
    def _is_low_quality_ask_response(
        cls,
        *,
        answer: str,
        question: str,
        current_definition: WorkflowDefinition | None,
    ) -> bool:
        normalized_answer = " ".join(str(answer or "").split()).strip().lower()
        if not normalized_answer:
            return True

        low_quality_markers = (
            "i could not generate a useful answer",
            "please rephrase your question",
            "please rephrase",
            "cannot answer that",
            "i'm not sure",
            "i can help in ask mode with",
        )
        if any(marker in normalized_answer for marker in low_quality_markers):
            return True

        node_focuses = cls._resolve_node_focuses_from_prompt(
            question.lower(),
            current_definition=current_definition,
            max_matches=3,
        )
        if node_focuses:
            mentions_focus = False
            for node_type in node_focuses:
                aliases = {
                    node_type,
                    node_type.replace("_", " "),
                    f"{node_type.replace('_', ' ')} node",
                }
                for alias in ASK_NODE_MANUAL_ALIASES.get(node_type, ()):
                    aliases.add(str(alias).strip().lower())
                if any(alias and alias in normalized_answer for alias in aliases):
                    mentions_focus = True
                    break
            if not mentions_focus and len(normalized_answer) < 220:
                return True

        too_generic_tokens = (
            "choose the right trigger",
            "share your goal",
            "best practices",
            "node combinations",
        )
        if len(normalized_answer) < 180 and any(
            token in normalized_answer for token in too_generic_tokens
        ):
            return True

        checklist = cls._evaluate_ask_quality_checklist(
            answer=normalized_answer,
            question=question,
            current_definition=current_definition,
        )
        checklist_score = sum(1 for passed in checklist.values() if passed)
        if checklist_score <= 2:
            return True
        if not checklist.get("correctness", False):
            return True

        return False

    @classmethod
    def _evaluate_ask_quality_checklist(
        cls,
        *,
        answer: str,
        question: str,
        current_definition: WorkflowDefinition | None,
    ) -> dict[str, bool]:
        normalized_answer = " ".join(str(answer or "").split()).strip().lower()
        lowered_question = " ".join(str(question or "").split()).strip().lower()

        node_focuses = cls._resolve_node_focuses_from_prompt(
            lowered_question,
            current_definition=current_definition,
            max_matches=3,
        )
        mention_aliases: set[str] = set()
        for node_type in node_focuses:
            mention_aliases.add(node_type)
            mention_aliases.add(node_type.replace("_", " "))
            for alias in ASK_NODE_MANUAL_ALIASES.get(node_type, ()):
                mention_aliases.add(str(alias).strip().lower())
        mentions_focus = any(
            alias and alias in normalized_answer for alias in mention_aliases
        ) if mention_aliases else False

        specificity = (
            len(normalized_answer) >= 160
            or mentions_focus
            or "in your current workflow" in normalized_answer
        )
        correctness = (
            not any(
                marker in normalized_answer
                for marker in (
                    "i could not generate a useful answer",
                    "please rephrase your question",
                    "cannot answer that",
                    "i'm not sure",
                )
            )
            and (mentions_focus or not node_focuses)
        )
        actionability = any(
            token in normalized_answer
            for token in (
                "where to place",
                "implementation steps",
                "parameter examples",
                "parameters",
                "next action",
                "1.",
                "2.",
            )
        )
        if current_definition is not None:
            workflow_tokens = {"workflow", "node", "edge"}
            workflow_tokens.update(
                str(node.id or "").strip().lower()
                for node in current_definition.nodes[:12]
                if str(node.id or "").strip()
            )
            context_use = any(token and token in normalized_answer for token in workflow_tokens)
        else:
            context_use = True

        return {
            "specificity": bool(specificity),
            "correctness": bool(correctness),
            "actionability": bool(actionability),
            "context_use": bool(context_use),
        }

    @classmethod
    def _build_local_ask_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        context_pack: str | None = None,
    ) -> str:
        lowered = prompt.lower()
        ask_intent = cls._classify_ask_intent(prompt)
        wants_brief = any(token in lowered for token in ("brief", "summary", "overview"))
        wants_upgrades = any(
            token in lowered
            for token in ("upgrade", "improve", "optimization", "optimize", "enhance", "better")
        )
        wants_steps = any(
            token in lowered
            for token in ("steps", "step by step", "how to implement", "implementation", "implement")
        )
        wants_place = any(
            token in lowered
            for token in ("where", "which place", "at which place", "where to place")
        )
        wants_parameters = any(
            token in lowered
            for token in ("parameter", "parameters", "config", "configuration")
        )
        routing_topic = any(
            token in lowered
            for token in ("if_else", "if else", "switch", "routing", "branch", "branching", "priority", "sentiment", "category path")
        )
        wants_implementation_guide = routing_topic and (wants_steps or wants_place or wants_parameters)
        node_focus_types = cls._resolve_node_focuses_from_prompt(
            lowered,
            current_definition=current_definition,
        )
        node_focus = node_focus_types[0] if node_focus_types else None
        workflow_context_requested = "workflow" in lowered or "this flow" in lowered
        wants_sequence_plan = any(
            token in lowered
            for token in (
                "which nodes",
                "node sequence",
                "in sequence",
                "connect in sequence",
                "steps",
                "step by step",
                "how to build",
                "create workflow",
                "build workflow",
                "i want to create",
            )
        )
        requested_channel_types = cls._infer_requested_channel_node_types(lowered)
        asks_workflow_blueprint = (
            ("workflow" in lowered or "flow" in lowered)
            and (
                wants_sequence_plan
                or "logical connection" in lowered
                or "connect" in lowered
                or len(requested_channel_types) >= 2
                or "lead generation" in lowered
                or "nurtur" in lowered
                or bool(re.search(r"\b\d+\s*day", lowered))
            )
        )
        asks_mail_format_improvement = (
            any(token in lowered for token in ("mail", "email", "gmail"))
            and any(token in lowered for token in ("format", "template", "improve", "improvement", "changes"))
        )
        asks_prompt_improvement = any(
            token in lowered
            for token in (
                "system prompt",
                "prompt is not good",
                "suggest good prompt",
                "suggest prompts",
                "improve prompt",
                "better prompt",
            )
        )
        asks_capabilities = any(
            token in lowered
            for token in (
                "ask mode capability",
                "ask mode capabilities",
                "what can ask mode",
                "what ask mode can",
                "chatbot capability",
                "what this chatbot can do",
                "all node",
                "all nodes",
            )
        )
        asks_trigger_recommendation = any(
            token in lowered
            for token in (
                "best trigger",
                "which trigger",
                "what trigger",
                "trigger for",
                "start trigger",
                "how to start workflow",
            )
        )
        asks_mapping_validation = ask_intent == "mapping_validate" or cls._looks_like_data_mapping_validation_prompt(prompt)
        asks_schema_contract = ask_intent == "schema_contract" or cls._looks_like_schema_contract_prompt(prompt)
        asks_merge_strategy = ask_intent == "merge_strategy" or cls._looks_like_merge_strategy_prompt(prompt)
        asks_loop_control = ask_intent == "loop_control" or cls._looks_like_loop_control_prompt(prompt)
        asks_trigger_configuration = ask_intent == "trigger_config" or cls._looks_like_trigger_configuration_prompt(prompt)
        asks_credential_oauth = ask_intent == "credential_oauth" or cls._looks_like_credential_oauth_prompt(prompt)
        asks_execution_log_debug = (
            ask_intent == "execution_log_debug"
            or cls._looks_like_execution_log_debug_prompt(prompt)
        )
        asks_reliability_patterns = (
            ask_intent == "reliability_patterns"
            or cls._looks_like_reliability_patterns_prompt(prompt)
        )
        asks_performance_scaling = (
            ask_intent == "performance_scaling"
            or cls._looks_like_performance_scaling_prompt(prompt)
        )
        asks_security_pii = (
            ask_intent == "security_pii"
            or cls._looks_like_security_pii_prompt(prompt)
        )
        asks_publish_ops = (
            ask_intent == "publish_ops"
            or cls._looks_like_publish_ops_prompt(prompt)
        )
        asks_n8n_migration = (
            ask_intent == "n8n_migration"
            or cls._looks_like_n8n_migration_prompt(prompt)
        )
        runtime_debug_requested = (
            asks_execution_log_debug
            or ask_intent == "debug"
            or cls._looks_like_runtime_error_prompt(prompt)
        )

        if (ask_intent == "routing" or wants_implementation_guide) and node_focus != "http_request":
            return cls._clip_assistant_message(
                cls._build_routing_implementation_response(
                    definition=current_definition,
                    include_brief=wants_brief,
                )
            )
        if asks_capabilities:
            return cls._clip_assistant_message(
                cls._build_ask_capabilities_response(current_definition=current_definition)
            )
        if asks_execution_log_debug:
            return cls._clip_assistant_message(
                cls._build_execution_log_debug_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_reliability_patterns:
            return cls._clip_assistant_message(
                cls._build_reliability_patterns_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_performance_scaling:
            return cls._clip_assistant_message(
                cls._build_performance_scaling_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_security_pii:
            return cls._clip_assistant_message(
                cls._build_security_pii_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_publish_ops:
            return cls._clip_assistant_message(
                cls._build_publish_ops_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_n8n_migration:
            return cls._clip_assistant_message(
                cls._build_n8n_migration_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_mapping_validation:
            return cls._clip_assistant_message(
                cls._build_data_mapping_validation_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_schema_contract and not runtime_debug_requested:
            return cls._clip_assistant_message(
                cls._build_schema_contract_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_merge_strategy and not runtime_debug_requested:
            return cls._clip_assistant_message(
                cls._build_merge_strategy_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_loop_control:
            return cls._clip_assistant_message(
                cls._build_loop_control_response(
                    prompt=prompt,
                    current_definition=current_definition,
                )
            )
        if asks_trigger_configuration:
            return cls._clip_assistant_message(
                cls._build_trigger_configuration_response(
                    prompt=prompt,
                    current_definition=current_definition,
                )
            )
        if asks_credential_oauth:
            return cls._clip_assistant_message(
                cls._build_credential_oauth_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_trigger_recommendation and not node_focus_types and ask_intent not in {"routing", "debug", "execution_log_debug"}:
            return cls._clip_assistant_message(
                cls._build_general_workflow_qa_response(
                    prompt=prompt,
                    current_definition=current_definition,
                )
            )
        if runtime_debug_requested:
            return cls._clip_assistant_message(
                cls._build_runtime_debug_response(
                    prompt=prompt,
                    current_definition=current_definition,
                    node_focus_types=node_focus_types,
                )
            )
        if asks_prompt_improvement:
            return cls._clip_assistant_message(
                cls._build_prompt_improvement_response(
                    prompt=prompt,
                    current_definition=current_definition,
                )
            )
        if asks_mail_format_improvement:
            return cls._clip_assistant_message(
                cls._build_email_format_improvement_response(
                    current_definition=current_definition,
                )
            )
        if asks_workflow_blueprint or (
            wants_sequence_plan and ask_intent in {"how_to", "general", "parameter_help"}
        ):
            return cls._clip_assistant_message(
                cls._build_workflow_sequence_response(
                    prompt=prompt,
                    current_definition=current_definition,
                )
            )
        if node_focus_types:
            if len(node_focus_types) > 1:
                return cls._clip_assistant_message(
                    cls._build_multi_node_focus_response(
                        node_types=node_focus_types,
                        prompt=prompt,
                        current_definition=current_definition,
                    )
                )
            return cls._clip_assistant_message(
                cls._build_node_focus_response(
                    node_type=node_focus,
                    prompt=prompt,
                    current_definition=current_definition,
                )
            )
        if ask_intent == "node_explain":
            return cls._clip_assistant_message(
                cls._build_unknown_node_explain_response(
                    prompt=prompt,
                    current_definition=current_definition,
                )
            )

        lines: list[str] = []
        if current_definition is not None and (wants_brief or (workflow_context_requested and not wants_steps)):
            lines.append("Workflow Brief:")
            for point in cls._render_workflow_brief_points(current_definition):
                lines.append(f"- {point}")

        if wants_upgrades or (current_definition is not None and workflow_context_requested and not wants_steps):
            lines.append("Suggested Upgrades:")
            for index, item in enumerate(
                cls._suggest_workflow_upgrades(current_definition),
                start=1,
            ):
                lines.append(f"{index}. {item}")

        if not lines:
            lines.append("Best-effort answer from available context:")
            if current_definition is not None:
                brief_points = cls._render_workflow_brief_points(current_definition)
                for point in brief_points[:2]:
                    lines.append(f"- {point}")
            else:
                lines.append("- No workflow JSON is attached, so I can only give platform-level guidance.")

            missing_items: list[str] = []
            if node_focus is None:
                missing_items.append("Which exact node should I explain (node id, label, or node type).")
            if ask_intent in {"debug", "execution_log_debug"}:
                missing_items.append("Latest failing node id and error message from execution logs.")
            if any(token in lowered for token in ("where", "place", "implement", "steps")):
                missing_items.append("Which source and target node ids you want this change between.")
            if not missing_items:
                missing_items.append("Your exact target outcome in one line (what should happen end-to-end).")
            missing_items = missing_items[:2]

            lines.append("What I still need to be exact:")
            for item in missing_items:
                lines.append(f"- {item}")

            next_action = (
                "Share: node id/label + your expected output. I will return exact placement and parameters."
                if current_definition is not None
                else "Share your workflow goal and start trigger; I will provide an exact node-by-node plan."
            )
            lines.append("Next action:")
            lines.append(f"- {next_action}")

            if context_pack:
                lines.append("Context used:")
                lines.append(f"- {cls._compact_json(context_pack, max_chars=220)}")

        return cls._clip_assistant_message("\n".join(lines))

    @classmethod
    def _extract_requested_node_name(cls, prompt: str) -> str:
        lowered = " ".join(str(prompt or "").lower().split()).strip()
        if not lowered:
            return ""

        patterns = (
            r"what does ([a-z0-9_ \-/]+?) node do",
            r"what is ([a-z0-9_ \-/]+?) node",
            r"explain ([a-z0-9_ \-/]+?) node",
            r"about ([a-z0-9_ \-/]+?) node",
            r"([a-z0-9_]+) node",
        )
        for pattern in patterns:
            match = re.search(pattern, lowered)
            if not match:
                continue
            candidate = re.sub(r"\s+", " ", str(match.group(1) or "").strip())
            candidate = candidate.strip(" .,:;!?")
            if candidate:
                return candidate
        return ""

    @classmethod
    def _closest_supported_node_types(
        cls,
        *,
        requested_node: str,
        max_results: int = 3,
    ) -> list[str]:
        query = str(requested_node or "").strip().lower()
        if not query:
            return []

        scored: list[tuple[float, str]] = []
        for node_type in NODE_CONFIG_DEFAULTS:
            aliases: set[str] = {
                node_type,
                node_type.replace("_", " "),
                f"{node_type.replace('_', ' ')} node",
            }
            aliases.update(
                str(alias).strip().lower()
                for alias in ASK_NODE_MANUAL_ALIASES.get(node_type, ())
            )

            best = 0.0
            for alias in aliases:
                if not alias:
                    continue
                if query == alias:
                    best = max(best, 1.0)
                    continue
                if query in alias or alias in query:
                    best = max(best, 0.92)
                similarity = SequenceMatcher(None, query, alias).ratio()
                best = max(best, similarity)
            if best >= 0.45:
                scored.append((best, node_type))

        scored.sort(key=lambda item: item[0], reverse=True)
        ordered: list[str] = []
        for _score, node_type in scored:
            if node_type in ordered:
                continue
            ordered.append(node_type)
            if len(ordered) >= max_results:
                break
        return ordered

    @classmethod
    def _build_unknown_node_explain_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        requested_node = cls._extract_requested_node_name(prompt)
        if current_definition is not None and requested_node:
            requested_normalized = requested_node.strip().lower()
            for node in current_definition.nodes:
                node_label = str(node.label or "").strip().lower()
                node_id = str(node.id or "").strip().lower()
                if requested_normalized and (
                    requested_normalized in node_label or requested_normalized == node_id
                ):
                    return cls._build_node_focus_response(
                        node_type=node.type,
                        prompt=prompt,
                        current_definition=current_definition,
                    )

        suggestions = cls._closest_supported_node_types(
            requested_node=requested_node or prompt
        )
        lines = [
            "Direct answer:",
            (
                f"- `{requested_node}` is not recognized as an Autoflow node type."
                if requested_node
                else "- I could not identify the exact node name in your question."
            ),
        ]

        if suggestions:
            lines.append("Closest supported nodes:")
            for index, node_type in enumerate(suggestions, start=1):
                details = NODE_TYPE_DETAILS.get(node_type, {})
                description = str(details.get("description") or "").strip() or f"{node_type} node."
                lines.append(f"{index}. `{node_type}`: {description}")

        lines.append("Next action:")
        lines.append("- Ask with exact node type or node id, for example: `Explain sort node` or `Explain read_google_docs node`.")
        if current_definition is not None:
            lines.append("In your current workflow:")
            lines.append(
                "- Available node ids/types: "
                + ", ".join(
                    f"{node.id}:{node.type}"
                    for node in current_definition.nodes[:8]
                    if str(node.id or "").strip()
                )
            )
        return "\n".join(lines)

    @classmethod
    def _looks_like_runtime_error_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False
        error_tokens = (
            "error",
            "fail",
            "failed",
            "failing",
            "problem",
            "issue",
            "runtime",
            "exception",
            "traceback",
            "timeout",
            "timed out",
            "not found",
            "bad gateway",
            "gateway timeout",
            "unauthorized",
            "forbidden",
            "rate limit",
            "too many requests",
            "connection refused",
            "dns",
            "status code",
            "invalid json",
            "json decode",
            "waiting",
            "stuck",
            "not run",
            "not running",
            "not execute",
            "not executing",
            "why false",
        )
        if any(token in lowered for token in error_tokens):
            return True
        return bool(re.search(r"\b(?:4\d{2}|5\d{2})\b", lowered))

    @classmethod
    def _looks_like_execution_log_debug_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        execution_tokens = (
            "execution log",
            "execution logs",
            "execution trace",
            "run log",
            "run logs",
            "run id",
            "execution id",
            "node id",
            "analyze execution",
        )
        debug_tokens = (
            "debug",
            "failed",
            "failing",
            "error",
            "fix",
            "why",
            "root cause",
            "exact failing edge",
            "failing edge",
            "runtime",
            "not working",
            "stuck",
            "waiting",
        )
        has_execution_topic = any(token in lowered for token in execution_tokens)
        has_debug_intent = any(token in lowered for token in debug_tokens)
        mentions_run_or_node_pattern = bool(
            re.search(r"\b(?:run|execution)\s*(?:id|#)\s*[:=]?\s*[a-z0-9][a-z0-9._:-]{2,}\b", lowered)
            or re.search(r"\bnode\s*(?:id|ids|#)\s*[:=]?\s*[a-z0-9][a-z0-9._:-]{1,}\b", lowered)
            or re.search(r"\bexecution\s+[a-z0-9][a-z0-9._:-]{2,}\b", lowered)
        )
        return has_execution_topic and (has_debug_intent or mentions_run_or_node_pattern)

    @staticmethod
    def _extract_execution_run_id(prompt: str) -> str | None:
        raw = str(prompt or "").strip()
        if not raw:
            return None

        patterns = (
            r"(?i)\b(?:run|execution)\s*(?:id|#)\s*[:=]?\s*([a-z0-9][a-z0-9._:-]{2,})\b",
            r"(?i)\bexecution\s+([a-z0-9][a-z0-9._:-]{2,})\b",
            r"\b([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\b",
        )
        for pattern in patterns:
            match = re.search(pattern, raw)
            if not match:
                continue
            candidate = str(match.group(1) or "").strip().strip(".,;:()[]{}")
            lowered_candidate = candidate.lower()
            if not candidate or lowered_candidate in {"id", "run", "execution", "node"}:
                continue
            return candidate
        return None

    @classmethod
    def _extract_execution_node_ids(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        max_items: int = 4,
    ) -> list[str]:
        lowered = str(prompt or "").lower()
        if not lowered:
            return []

        collected: list[str] = []
        seen: set[str] = set()

        def _append(candidate: str) -> None:
            normalized = str(candidate or "").strip().strip(".,;:()[]{}")
            if not normalized:
                return
            key = normalized.lower()
            if key in {"node", "id", "ids", "run", "execution", "and", "or"}:
                return
            if key in seen:
                return
            seen.add(key)
            collected.append(normalized)

        for match in re.finditer(
            r"(?i)\bnode\s*(?:id|ids|#)\s*[:=]?\s*([a-z0-9][a-z0-9._:-]{1,}(?:\s*,\s*[a-z0-9][a-z0-9._:-]{1,})*)",
            lowered,
        ):
            fragment = str(match.group(1) or "")
            for token in re.split(r"\s*,\s*", fragment):
                _append(token)

        if current_definition is not None:
            for node in current_definition.nodes:
                node_id = str(node.id or "").strip()
                if not node_id:
                    continue
                pattern = rf"(?<![a-z0-9_]){re.escape(node_id.lower())}(?![a-z0-9_])"
                if re.search(pattern, lowered):
                    _append(node_id)

        return collected[: max(1, max_items)]

    @staticmethod
    def _extract_error_excerpt(prompt: str, *, max_chars: int = 280) -> str:
        raw = str(prompt or "").strip()
        if not raw:
            return ""
        compact_lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not compact_lines:
            return ""
        patterns = (
            r"(?i)(http request failed:[^\n]+)",
            r"(?i)(error:[^\n]+)",
            r"(?i)(failed:[^\n]+)",
            r"(?i)(status code\s*\d{3}[^\n]*)",
        )
        for pattern in patterns:
            match = re.search(pattern, raw)
            if match:
                return " ".join(match.group(1).split())[:max_chars]
        for line in compact_lines:
            lowered = line.lower()
            if any(
                token in lowered
                for token in (
                    "error",
                    "failed",
                    "timeout",
                    "not found",
                    "bad gateway",
                    "status code",
                    "exception",
                )
            ):
                return " ".join(line.split())[:max_chars]
        return " ".join(compact_lines[-1].split())[:max_chars]

    @classmethod
    def _classify_error_signature(cls, prompt: str) -> dict[str, Any]:
        lowered = str(prompt or "").lower()
        status_match = re.search(r"\b([1-5]\d{2})\b", lowered)
        status_code = int(status_match.group(1)) if status_match else None

        kind = "generic_runtime"
        summary = "This is a runtime execution failure. It usually means one node config or upstream data shape is not matching what the node expects."
        causes = [
            "A required config value is missing or invalid for the failing node.",
            "Upstream output fields do not match the templates used in downstream nodes.",
            "External integration credentials, endpoint, or payload contract has changed.",
        ]
        fixes = [
            "Open the failing node execution log and verify the exact node id + error message.",
            "Check required config keys on that node and confirm template fields resolve from upstream output.",
            "Re-run with one sample payload and inspect output at each node boundary.",
        ]

        if status_code == 404 or "not found" in lowered:
            kind = "not_found"
            summary = "HTTP 404 Not Found means the target URL/path/resource does not exist for the request being sent."
            causes = [
                "The base URL or endpoint path is wrong (typo, missing version like /v1, or wrong environment domain).",
                "Method/path mismatch, for example calling GET on a POST-only endpoint.",
                "Resource identifier in URL path/query is empty or invalid.",
            ]
            fixes = [
                "Verify `url` exactly as API docs specify, including version and path segment.",
                "Confirm `method` matches endpoint contract and required query/path params are present.",
                "Test the same request in Postman/curl, then copy working URL/method back into the node.",
            ]
        elif status_code in {401, 403} or "unauthorized" in lowered or "forbidden" in lowered:
            kind = "auth"
            summary = "This is an authentication/authorization failure. The endpoint is reachable but credentials or access scope are invalid."
            causes = [
                "Missing/expired token or wrong credential selected in node config.",
                "Token format mismatch (for example missing Bearer prefix).",
                "API key lacks permission for this endpoint.",
            ]
            fixes = [
                "Re-select the correct credential and refresh/reissue token if needed.",
                "Verify `auth_mode` and auth headers exactly match provider documentation.",
                "Confirm account/app has permission for the called endpoint.",
            ]
        elif status_code == 422 or "validation" in lowered or "unprocessable" in lowered:
            kind = "payload_validation"
            summary = "The request reached the service, but payload fields failed validation."
            causes = [
                "Wrong field names/data types in body or query.",
                "Required fields are missing after template resolution.",
                "Date/time/enum values are not in the expected format.",
            ]
            fixes = [
                "Log final payload right before the outbound node and compare with API schema.",
                "Fix mapping keys and data types in templates (string vs number vs boolean).",
                "Add a code/filter validation step before outbound call for required fields.",
            ]
        elif status_code == 429 or "rate limit" in lowered or "too many requests" in lowered:
            kind = "rate_limit"
            summary = "The integration is being rate-limited (too many requests)."
            causes = [
                "Request burst exceeded provider limits.",
                "No delay/backoff between retries.",
                "Multiple workflow runs hit the same endpoint concurrently.",
            ]
            fixes = [
                "Add delay + retry with exponential backoff.",
                "Throttle schedule/concurrency and avoid duplicate trigger bursts.",
                "Implement fallback path when retries are exhausted.",
            ]
        elif status_code in {500, 502, 503, 504} or any(
            token in lowered for token in ("bad gateway", "gateway timeout", "service unavailable")
        ):
            kind = "server_or_gateway"
            summary = "This is an upstream server/gateway failure. Your request may be valid but the target service is unstable or unreachable."
            causes = [
                "Temporary provider outage or upstream gateway issue.",
                "Timeout due to slow downstream response.",
                "Request size/payload complexity causing backend failure.",
            ]
            fixes = [
                "Retry with delay/backoff and set a practical timeout value.",
                "Check provider status page/logs and re-run after short interval.",
                "Reduce payload size and avoid unnecessary fields.",
            ]
        elif any(token in lowered for token in ("timeout", "timed out", "connection refused", "dns")):
            kind = "network_or_timeout"
            summary = "This is a network/timeout failure while reaching a dependency."
            causes = [
                "Host is unreachable, DNS resolution failed, or firewall restrictions apply.",
                "Timeout is too low for endpoint response time.",
                "Endpoint requires VPN/private network that runner cannot access.",
            ]
            fixes = [
                "Verify host reachability and DNS from runtime environment.",
                "Increase timeout and add retry with delay.",
                "Use the correct network route/environment endpoint.",
            ]
        elif "waiting" in lowered and "merge" in lowered:
            kind = "merge_waiting"
            summary = "The merge node is waiting because configured inputs do not all receive data in the same run."
            causes = [
                "Merge mode expects multiple inputs (`combine`/`append`) but one branch never executes.",
                "`input_count` is higher than active incoming branches.",
                "Branching logic routes only one side while merge waits for both.",
            ]
            fixes = [
                "Set merge mode/inputs to match actual branch behavior in this run.",
                "For mutually exclusive branches, route both branches into a mode that does not block on absent input.",
                "Ensure every branch reaching merge has consistent execution path or add separate merge per route.",
            ]
        elif any(token in lowered for token in ("why false", "false branch", "if else")):
            kind = "branch_condition"
            summary = "The condition evaluated to false because compared field/value or type did not match at runtime."
            causes = [
                "Field path points to missing or wrong key.",
                "Type mismatch (string 'true' vs boolean true, case mismatch, whitespace).",
                "Condition compares against value that never occurs in actual payload.",
            ]
            fixes = [
                "Inspect the previous node output and verify exact field path.",
                "Normalize value in code/filter step before `if_else` (trim/lower/type-cast).",
                "Update operator/value to match actual runtime values.",
            ]
        elif any(token in lowered for token in ("template", "{{", "undefined", "keyerror", "missing key")):
            kind = "template_mapping"
            summary = "The runtime failed because one or more template variables do not exist in current input data."
            causes = [
                "Template references outdated field path after node changes.",
                "AI output key used directly instead of `{{output.<key>}}` where required.",
                "Branch-specific fields are referenced in paths where branch does not run.",
            ]
            fixes = [
                "Map templates to fields that exist in immediate upstream output.",
                "For ai_agent outputs use `{{output.<field>}}` consistently.",
                "Add safe defaults or branch-specific mappings before outbound nodes.",
            ]

        return {
            "status_code": status_code,
            "kind": kind,
            "summary": summary,
            "causes": causes,
            "fixes": fixes,
        }

    @classmethod
    def _build_node_debug_checks(
        cls,
        *,
        node_type: str,
        error_kind: str,
    ) -> list[str]:
        if node_type == "http_request":
            return [
                "Check `url`, `method`, and `auth_mode` first; then verify `body_type` and `body_json`/`body_form_json` mapping.",
                "If API expects JSON, ensure `body_type=json` and `body_json` is valid JSON with resolved templates.",
                "Confirm `headers_json` includes required content-type/auth headers.",
            ]
        if node_type == "merge":
            return [
                "Check `mode` and `input_count`; waiting issues happen when a configured input branch does not emit data.",
                "If branch is exclusive (`if_else`), avoid merge settings that block for both branches on every run.",
                "Verify each incoming edge targetHandle matches expected merge inputs.",
            ]
        if node_type in {"if_else", "switch", "filter"}:
            return [
                "Verify condition field path exists in runtime payload.",
                "Align `operator`, `data_type`, and `case_sensitive` with actual values.",
                "Use a code node to normalize values before routing when source payload is inconsistent.",
            ]
        if node_type == "ai_agent":
            return [
                "Confirm ai_agent has a connected chat model using targetHandle `chat_model`.",
                "Keep output mappings as `{{output.<key>}}` in downstream nodes.",
                "Reduce temperature for stable structured outputs when routing depends on exact keys.",
            ]
        if node_type in {"send_gmail_message", "telegram", "whatsapp", "slack_send_message", "linkedin"}:
            return [
                "Check credential binding and required destination fields before execution.",
                "Ensure message template variables exist in current input payload.",
                "Enable retry/fallback path so one delivery failure does not block workflow completion.",
            ]
        if node_type in {"search_update_google_sheets", "create_google_sheets"}:
            return [
                "Verify spreadsheet id/sheet name and operation-specific required fields.",
                "Check `update_mappings` column names exactly match sheet headers.",
                "Use `auto_create_headers` or pre-create headers to avoid mapping misses.",
            ]
        if node_type == "code":
            return [
                "Guard optional keys (`dict.get`) to prevent runtime key errors.",
                "Return `output` as dict consistently for downstream template access.",
                "Log intermediate payload shape for one run while debugging.",
            ]
        if node_type in {"file_write", "file_read"}:
            return [
                "Validate file path and permissions in runtime environment.",
                "Check `input_key`/content source mapping for missing data.",
                "Use `create_dirs=true` when writing nested paths.",
            ]
        defaults = NODE_CONFIG_DEFAULTS.get(node_type, {})
        key_preview = ", ".join(list(defaults.keys())[:4]) if isinstance(defaults, Mapping) else ""
        fallback = [
            "Validate required config and credential fields for this node.",
            "Confirm upstream output contains every template variable referenced here.",
            "Run a single test payload and inspect this node input/output in execution logs.",
        ]
        if key_preview:
            fallback.insert(0, f"Check these core keys first: {key_preview}.")
        if error_kind == "template_mapping":
            fallback.insert(0, "Prioritize fixing template field paths for this node before retrying.")
        return fallback[:4]

    @classmethod
    def _build_runtime_debug_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        signature = cls._classify_error_signature(prompt)
        error_excerpt = cls._extract_error_excerpt(prompt)
        focus_types = node_focus_types[:3]
        likely_nodes = cls._pick_likely_failing_nodes(
            prompt=prompt,
            current_definition=current_definition,
            node_focus_types=focus_types,
            error_kind=str(signature["kind"]),
        )
        if likely_nodes:
            focus_types = [
                node.type
                for node in likely_nodes
                if str(node.type or "").strip()
            ][:3] or focus_types

        lines: list[str] = [
            "Direct answer:",
            f"- {signature['summary']}",
        ]
        if error_excerpt:
            lines.append("Detected error:")
            lines.append(f"- {error_excerpt}")

        if likely_nodes:
            lines.append("Likely failing node(s):")
            for node in likely_nodes[:3]:
                lines.append(f"- {node.label} ({node.id}) type={node.type}")

        if current_definition is not None:
            nodes_by_id = {node.id: node for node in current_definition.nodes}
            matched_nodes = [
                node for node in current_definition.nodes if node.type in set(focus_types)
            ][:3]
            if not matched_nodes:
                matched_nodes = [
                    node
                    for node in current_definition.nodes
                    if node.type not in TRIGGER_NODE_TYPES and node.type not in AI_CHAT_MODEL_NODE_TYPES
                ][:2]
            if matched_nodes:
                lines.append("In your current workflow:")
                for node in matched_nodes:
                    lines.append(f"- {node.label} ({node.id}) type={node.type}")
                    incoming = [edge for edge in current_definition.edges if edge.target == node.id][:2]
                    outgoing = [edge for edge in current_definition.edges if edge.source == node.id][:2]
                    anchor = cls._build_node_anchor_line(
                        node_id=node.id,
                        incoming_edges=incoming,
                        outgoing_edges=outgoing,
                        nodes_by_id=nodes_by_id,
                    )
                    if anchor:
                        lines.append(f"  placement anchor: {anchor}")

        lines.append("Likely root causes:")
        for index, cause in enumerate(signature["causes"][:3], start=1):
            lines.append(f"{index}. {cause}")

        lines.append("Fast triage order:")
        for index, step in enumerate(signature["fixes"][:3], start=1):
            lines.append(f"{index}. {step}")

        lines.append("Fix steps:")
        if focus_types:
            unique_types: list[str] = []
            for node_type in focus_types:
                if node_type not in unique_types:
                    unique_types.append(node_type)
            for node_type in unique_types:
                checks = cls._build_node_debug_checks(
                    node_type=node_type,
                    error_kind=str(signature["kind"]),
                )
                lines.append(f"- For `{node_type}`:")
                for idx, item in enumerate(checks[:3], start=1):
                    lines.append(f"  {idx}. {item}")
        else:
            for index, step in enumerate(signature["fixes"][:3], start=1):
                lines.append(f"{index}. {step}")

        lines.append("Validation checklist:")
        lines.append("1. Re-run one sample input and confirm the failing node executes successfully.")
        lines.append("2. Verify downstream node receives expected fields (especially template values).")
        lines.append("3. Confirm final branch/output reaches target node without waiting/stuck state.")

        lines.append("If it still fails, share:")
        lines.append("- Failing node id + full error line from execution log.")
        lines.append("- One redacted sample input payload and expected output.")

        return "\n".join(lines)

    @classmethod
    def _resolve_candidate_failing_edges(
        cls,
        *,
        current_definition: WorkflowDefinition | None,
        node_ids: list[str],
        max_edges: int = 6,
    ) -> list[Any]:
        if current_definition is None:
            return []

        target_ids = {
            str(node_id or "").strip()
            for node_id in node_ids
            if str(node_id or "").strip()
        }
        if not target_ids:
            return []

        selected: list[Any] = []
        seen: set[str] = set()
        for edge in current_definition.edges:
            source_id = str(edge.source or "").strip()
            target_id = str(edge.target or "").strip()
            if source_id not in target_ids and target_id not in target_ids:
                continue
            edge_id = str(edge.id or "").strip() or (
                f"{source_id}->{target_id}:{edge.sourceHandle}:{edge.targetHandle}:{edge.branch}"
            )
            if edge_id in seen:
                continue
            seen.add(edge_id)
            selected.append(edge)
            if len(selected) >= max_edges:
                break

        return selected

    @classmethod
    def _build_execution_log_debug_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        signature = cls._classify_error_signature(prompt)
        error_excerpt = cls._extract_error_excerpt(prompt)
        run_id = cls._extract_execution_run_id(prompt)
        explicit_node_ids = cls._extract_execution_node_ids(
            prompt=prompt,
            current_definition=current_definition,
        )
        focus_types = node_focus_types[:3]
        likely_nodes = cls._pick_likely_failing_nodes(
            prompt=prompt,
            current_definition=current_definition,
            node_focus_types=focus_types,
            error_kind=str(signature["kind"]),
        )

        nodes_by_id: dict[str, Any] = {}
        nodes_by_lower_id: dict[str, Any] = {}
        if current_definition is not None:
            for node in current_definition.nodes:
                node_id = str(node.id or "").strip()
                if not node_id:
                    continue
                nodes_by_id[node_id] = node
                nodes_by_lower_id[node_id.lower()] = node

        focus_nodes: list[Any] = []
        seen_focus_ids: set[str] = set()

        def _append_focus(node: Any | None) -> None:
            if node is None:
                return
            node_id = str(node.id or "").strip()
            if not node_id or node_id in seen_focus_ids:
                return
            seen_focus_ids.add(node_id)
            focus_nodes.append(node)

        for node_id in explicit_node_ids:
            node = nodes_by_id.get(node_id) or nodes_by_lower_id.get(node_id.lower())
            _append_focus(node)
        for node in likely_nodes:
            _append_focus(node)

        if focus_nodes:
            focus_types = []
            for node in focus_nodes:
                node_type = str(node.type or "").strip()
                if node_type and node_type not in focus_types:
                    focus_types.append(node_type)
                if len(focus_types) >= 3:
                    break

        candidate_node_ids = [str(node.id or "").strip() for node in focus_nodes if str(node.id or "").strip()]
        if not candidate_node_ids:
            candidate_node_ids = explicit_node_ids[:]
        candidate_edges = cls._resolve_candidate_failing_edges(
            current_definition=current_definition,
            node_ids=candidate_node_ids,
            max_edges=6,
        )

        lines: list[str] = [
            "Direct answer:",
            "- I can debug this with execution-log context and point to likely failing edges plus exact fix steps.",
            f"- {signature['summary']}",
            "Execution log context:",
            f"- Run id: `{run_id}`" if run_id else "- Run id: not provided.",
            (
                "- Referenced node id(s): "
                + ", ".join(f"`{node_id}`" for node_id in explicit_node_ids[:4])
            ) if explicit_node_ids else "- Referenced node id(s): not provided.",
        ]
        if error_excerpt:
            lines.append("Detected error:")
            lines.append(f"- {error_excerpt}")

        if focus_nodes:
            lines.append("Likely failing node(s):")
            for node in focus_nodes[:3]:
                lines.append(f"- {node.label} ({node.id}) type={node.type}")

        if current_definition is not None:
            lines.append("In your current workflow:")
            lines.append(
                f"- Context has {len(current_definition.nodes)} nodes and {len(current_definition.edges)} edges."
            )

        if candidate_edges:
            lines.append("Exact failing-edge candidates:")
            for edge in candidate_edges[:6]:
                source_id = str(edge.source or "").strip()
                target_id = str(edge.target or "").strip()
                source_node = nodes_by_id.get(source_id)
                target_node = nodes_by_id.get(target_id)
                source_label = str(source_node.label if source_node is not None else source_id).strip()
                target_label = str(target_node.label if target_node is not None else target_id).strip()
                edge_line = f"- {source_label} ({source_id}) -> {target_label} ({target_id})"
                edge_meta: list[str] = []
                edge_id = str(edge.id or "").strip()
                if edge_id:
                    edge_meta.append(f"edge_id={edge_id}")
                branch = str(edge.branch or "").strip()
                if branch:
                    edge_meta.append(f"branch={branch}")
                source_handle = str(edge.sourceHandle or "").strip()
                if source_handle:
                    edge_meta.append(f"sourceHandle={source_handle}")
                target_handle = str(edge.targetHandle or "").strip()
                if target_handle:
                    edge_meta.append(f"targetHandle={target_handle}")
                if edge_meta:
                    edge_line += " [" + ", ".join(edge_meta) + "]"
                lines.append(edge_line)
        elif current_definition is not None:
            lines.append("Exact failing-edge candidates:")
            lines.append("- Could not infer a precise edge from prompt-only context; use run log failure event to pin source->target edge.")

        lines.append("Likely root causes:")
        for index, cause in enumerate(signature["causes"][:3], start=1):
            lines.append(f"{index}. {cause}")

        lines.append("Edge-focused fix steps:")
        lines.append(
            "1. Open this execution and confirm the first failed node event, then match it with the candidate edge right before that node."
        )
        lines.append(
            "2. Verify edge branch/handles (`branch`, `sourceHandle`, `targetHandle`) align with node config expectations."
        )
        if focus_types:
            unique_types: list[str] = []
            for node_type in focus_types:
                if node_type not in unique_types:
                    unique_types.append(node_type)
            for node_type in unique_types[:3]:
                checks = cls._build_node_debug_checks(
                    node_type=node_type,
                    error_kind=str(signature["kind"]),
                )
                if checks:
                    lines.append(f"3. `{node_type}` check: {checks[0]}")
                    break
        else:
            lines.append("3. Re-run with one redacted sample payload and inspect the failing node input/output diff.")

        lines.append("Validation checklist:")
        lines.append("1. Re-run the same payload and confirm failure no longer occurs on the same edge.")
        lines.append("2. Confirm downstream node receives required fields after the fixed edge.")
        lines.append("3. Verify workflow reaches terminal output without waiting/stuck state.")

        missing: list[str] = []
        if not run_id:
            missing.append("execution run id")
        if not explicit_node_ids:
            missing.append("failing node id")
        if missing:
            lines.append("Missing info for exact pinpoint:")
            for item in missing[:2]:
                lines.append(f"- {item}")
            lines.append("Next action:")
            lines.append("- Share run id + failing node id from execution panel for an exact source->target fix.")

        return "\n".join(lines)

    @classmethod
    def _looks_like_reliability_patterns_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        pattern_tokens = (
            "retry",
            "retries",
            "backoff",
            "exponential backoff",
            "fallback",
            "failover",
            "idempotent",
            "idempotency",
            "duplicate send",
            "duplicate event",
            "duplicate run",
            "exactly once",
            "at least once",
            "resilience",
            "reliable",
            "reliability",
            "fault tolerant",
            "circuit breaker",
            "dead letter",
            "dlq",
        )
        action_tokens = (
            "how to",
            "how do i",
            "add",
            "implement",
            "design",
            "pattern",
            "strategy",
            "best practice",
            "safe",
            "harden",
            "improve",
            "upgrade",
        )
        has_pattern = any(token in lowered for token in pattern_tokens)
        has_action = any(token in lowered for token in action_tokens)
        return has_pattern and (has_action or "?" in lowered)

    @classmethod
    def _pick_reliability_focus_nodes(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> list[Any]:
        if current_definition is None:
            return []

        lowered_prompt = str(prompt or "").lower()
        nodes = list(current_definition.nodes)
        selected: list[Any] = []
        seen_ids: set[str] = set()

        def _append(node: Any) -> None:
            node_id = str(node.id or "").strip()
            if not node_id or node_id in seen_ids:
                return
            seen_ids.add(node_id)
            selected.append(node)

        focus_set = set(node_focus_types)
        for node in nodes:
            if node.type in focus_set and node.type in RELIABILITY_PATTERN_NODE_TYPES:
                _append(node)

        for node in nodes:
            node_id = str(node.id or "").strip().lower()
            node_label = str(node.label or "").strip().lower()
            if node_id and f" {node_id} " in f" {lowered_prompt} " and node.type in RELIABILITY_PATTERN_NODE_TYPES:
                _append(node)
                continue
            if node_label and f" {node_label} " in f" {lowered_prompt} " and node.type in RELIABILITY_PATTERN_NODE_TYPES:
                _append(node)

        for node in nodes:
            if node.type in RELIABILITY_PATTERN_NODE_TYPES:
                _append(node)
                if len(selected) >= 4:
                    break

        return selected[:4]

    @classmethod
    def _build_reliability_patterns_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        lowered = str(prompt or "").lower()
        asks_retry = any(token in lowered for token in ("retry", "retries", "retry policy", "attempt"))
        asks_backoff = any(token in lowered for token in ("backoff", "exponential", "delay"))
        asks_fallback = any(token in lowered for token in ("fallback", "failover", "secondary", "backup channel"))
        asks_idempotency = any(
            token in lowered
            for token in ("idempotency", "idempotent", "duplicate", "exactly once", "at least once")
        )
        if not any((asks_retry, asks_backoff, asks_fallback, asks_idempotency)):
            asks_retry = True
            asks_backoff = True
            asks_fallback = True
            asks_idempotency = True

        focus_nodes = cls._pick_reliability_focus_nodes(
            prompt=prompt,
            current_definition=current_definition,
            node_focus_types=node_focus_types,
        )

        lines: list[str] = [
            "Direct answer:",
            "- Use a 4-layer reliability pattern: bounded retry, backoff delay, explicit fallback path, and idempotency guard.",
            "Reliability design pattern:",
            "1. Keep one primary action node (HTTP/channel) with deterministic input and timeout.",
        ]
        if asks_retry:
            lines.append("2. Add bounded retries (for example max 3 attempts) so transient failures can recover without infinite loops.")
        if asks_backoff:
            lines.append("3. Add `delay` between retries and increase wait time per attempt (simple exponential/backoff progression).")
        if asks_fallback:
            lines.append("4. If final retry fails, route to fallback channel/storage so workflow still completes safely.")
        if asks_idempotency:
            lines.append("5. Add idempotency key check before outbound send to prevent duplicate processing.")

        lines.append("Recommended config snippets:")
        if asks_retry or asks_backoff:
            lines.append("- Retry gate (`if_else`):")
            lines.append(
                f"  `{cls._compact_json({'field': 'attempt_count', 'operator': 'less_than', 'value': '3', 'value_mode': 'literal', 'case_sensitive': False}, max_chars=280)}`"
            )
            lines.append("- Delay node (`delay`) example:")
            lines.append(f"  `{cls._compact_json({'amount': '30', 'unit': 'seconds'}, max_chars=160)}`")
        if asks_fallback:
            lines.append("- Fallback routing (`if_else` after retry result):")
            lines.append(
                f"  `{cls._compact_json({'field': 'success', 'operator': 'equals', 'value': 'false', 'value_mode': 'literal', 'case_sensitive': False}, max_chars=280)}`"
            )
        if asks_idempotency:
            lines.append("- Idempotent write (`search_update_google_sheets` upsert) example:")
            lines.append(
                f"  `{cls._compact_json({'operation': 'upsert_row', 'key_column': 'Idempotency Key', 'key_value': '{{event_id}}', 'upsert_if_not_found': True}, max_chars=320)}`"
            )

        if current_definition is not None:
            nodes_by_id = {
                str(node.id or "").strip(): node
                for node in current_definition.nodes
                if str(node.id or "").strip()
            }
            has_delay = any(node.type == "delay" for node in current_definition.nodes)
            has_router = any(node.type in {"if_else", "switch"} for node in current_definition.nodes)
            has_idempotent_upsert = any(
                node.type == "search_update_google_sheets"
                and isinstance(node.config, Mapping)
                and str(node.config.get("operation") or "").strip() == "upsert_row"
                and bool(str(node.config.get("key_column") or "").strip())
                and bool(str(node.config.get("key_value") or "").strip())
                for node in current_definition.nodes
            )

            lines.append("In your current workflow:")
            lines.append(
                f"- Reliability controls present: delay={str(has_delay).lower()}, routing={str(has_router).lower()}, idempotent_upsert={str(has_idempotent_upsert).lower()}."
            )
            if focus_nodes:
                for node in focus_nodes[:3]:
                    lines.append(f"- {node.label} ({node.id}) type={node.type}")
                    incoming = [edge for edge in current_definition.edges if edge.target == node.id][:2]
                    outgoing = [edge for edge in current_definition.edges if edge.source == node.id][:2]
                    anchor = cls._build_node_anchor_line(
                        node_id=node.id,
                        incoming_edges=incoming,
                        outgoing_edges=outgoing,
                        nodes_by_id=nodes_by_id,
                    )
                    if anchor:
                        lines.append(f"  placement anchor: {anchor}")
                    if node.type == "http_request":
                        lines.append("  placement: add retry gate immediately after this node, then `delay`, then retry branch.")
                    elif node.type in {"telegram", "whatsapp", "send_gmail_message", "slack_send_message", "linkedin"}:
                        lines.append("  placement: keep this as primary delivery; add fallback delivery node on final failure branch.")
                    elif node.type in {"search_update_google_sheets", "create_google_sheets", "file_write"}:
                        lines.append("  placement: store idempotency key + delivery status before/after outbound nodes.")
            else:
                lines.append("- No reliability-critical outbound node detected yet; add pattern around your first external integration node.")

        lines.append("Validation checklist:")
        lines.append("1. Force one transient failure and confirm retry + delay sequence executes as expected.")
        lines.append("2. Force persistent failure and confirm fallback branch runs without blocking final workflow completion.")
        lines.append("3. Re-send same event id and confirm idempotency guard prevents duplicate side effects.")
        return "\n".join(lines)

    @classmethod
    def _looks_like_performance_scaling_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        strong_performance_tokens = (
            "performance",
            "scaling",
            "scale",
            "optimize",
            "optimization",
            "faster",
            "speed up",
            "slow",
            "latency",
            "throughput",
            "api calls",
            "too many calls",
            "reduce calls",
            "cost",
            "token usage",
            "high load",
            "heavy workflow",
        )
        action_tokens = (
            "how to",
            "how do i",
            "reduce",
            "improve",
            "tune",
            "optimize",
            "best way",
            "what should",
            "what can",
            "guide",
            "plan",
        )
        debug_failure_tokens = (
            "error",
            "failed",
            "failing",
            "stuck",
            "waiting",
            "exception",
            "status code",
            "not working",
            "problem",
            "issue",
        )
        has_performance_signal = any(token in lowered for token in strong_performance_tokens)
        has_runtime_tuning_signal = "runtime" in lowered and any(
            token in lowered for token in ("reduce runtime", "improve runtime", "optimize runtime", "faster runtime")
        )
        has_action_signal = any(token in lowered for token in action_tokens)
        has_debug_failure_bias = any(token in lowered for token in debug_failure_tokens)
        if has_debug_failure_bias and not has_performance_signal:
            return False
        return (has_performance_signal or has_runtime_tuning_signal) and (has_action_signal or "?" in lowered)

    @classmethod
    def _pick_performance_focus_nodes(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> list[Any]:
        if current_definition is None:
            return []

        lowered_prompt = str(prompt or "").lower()
        nodes = list(current_definition.nodes)
        selected: list[Any] = []
        seen_ids: set[str] = set()

        def _append(node: Any) -> None:
            node_id = str(node.id or "").strip()
            if not node_id or node_id in seen_ids:
                return
            seen_ids.add(node_id)
            selected.append(node)

        focus_set = set(node_focus_types)
        for node in nodes:
            if node.type in focus_set and node.type in PERFORMANCE_SENSITIVE_NODE_TYPES:
                _append(node)

        for node in nodes:
            node_id = str(node.id or "").strip().lower()
            node_label = str(node.label or "").strip().lower()
            if node_id and f" {node_id} " in f" {lowered_prompt} " and node.type in PERFORMANCE_SENSITIVE_NODE_TYPES:
                _append(node)
                continue
            if node_label and f" {node_label} " in f" {lowered_prompt} " and node.type in PERFORMANCE_SENSITIVE_NODE_TYPES:
                _append(node)

        preferred_types = (
            "http_request",
            "ai_agent",
            "image_gen",
            "merge",
            "search_update_google_sheets",
            "send_gmail_message",
            "telegram",
            "whatsapp",
            "linkedin",
        )
        for preferred_type in preferred_types:
            for node in nodes:
                if node.type == preferred_type:
                    _append(node)
                    if len(selected) >= 5:
                        break
            if len(selected) >= 5:
                break

        return selected[:5]

    @classmethod
    def _build_performance_scaling_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        lowered = str(prompt or "").lower()
        focus_nodes = cls._pick_performance_focus_nodes(
            prompt=prompt,
            current_definition=current_definition,
            node_focus_types=node_focus_types,
        )

        asks_api_reduction = any(
            token in lowered
            for token in ("api calls", "reduce calls", "too many calls", "cost", "quota")
        )
        asks_runtime_speed = any(
            token in lowered
            for token in ("runtime", "latency", "faster", "speed", "slow", "throughput")
        )
        asks_scale = any(
            token in lowered
            for token in ("scale", "scaling", "high load", "concurrency")
        )

        lines: list[str] = [
            "Direct answer:",
            "- Use a performance-first chain: reduce input volume early, avoid unnecessary expensive calls, and control fan-out/concurrency.",
            "Performance and scaling plan:",
            "1. Filter/limit data before costly nodes (`ai_agent`, `image_gen`, external channels).",
            "2. Collapse duplicate outbound operations and keep only required API calls per run.",
            "3. Keep AI output compact (strict keys + lower max tokens) to reduce latency and cost.",
            "4. Add cache/idempotency key for repeated events so duplicate runs skip repeated API work.",
            "5. Add runtime observability fields (`started_at`, `duration_ms`, `api_call_count`, `retry_count`).",
        ]
        if asks_api_reduction:
            lines.append("6. For API-heavy flows, batch writes where possible and avoid calling the same endpoint twice per item.")
        if asks_runtime_speed:
            lines.append("7. For runtime reduction, push condition routing earlier so non-required branches never execute.")
        if asks_scale:
            lines.append("8. For scaling, throttle trigger frequency/concurrency and prefer queue-like fan-in/fan-out guards.")

        lines.append("Recommended tuning snippets:")
        lines.append("- Early limit (`limit`):")
        lines.append(
            f"  `{cls._compact_json({'input_key': 'items', 'limit': 10, 'offset': 0, 'start_from': 'start'}, max_chars=220)}`"
        )
        lines.append("- HTTP timeout + fail-fast (`http_request`):")
        lines.append(
            f"  `{cls._compact_json({'timeout_seconds': 20, 'follow_redirects': True, 'continue_on_fail': False}, max_chars=220)}`"
        )
        lines.append("- AI budget guard (`chat_model_openai` or `chat_model_groq`):")
        lines.append(
            f"  `{cls._compact_json({'temperature': 0.2, 'max_tokens': 300}, max_chars=180)}`"
        )

        if current_definition is not None:
            nodes_by_id = {
                str(node.id or "").strip(): node
                for node in current_definition.nodes
                if str(node.id or "").strip()
            }
            api_like_types = {
                "http_request",
                "send_gmail_message",
                "telegram",
                "whatsapp",
                "slack_send_message",
                "linkedin",
                "search_update_google_sheets",
                "read_google_sheets",
                "create_google_docs",
                "read_google_docs",
                "update_google_docs",
                "image_gen",
            }
            api_node_count = sum(1 for node in current_definition.nodes if node.type in api_like_types)
            ai_node_count = sum(1 for node in current_definition.nodes if node.type in {"ai_agent", "image_gen"})
            has_early_limit = any(node.type == "limit" for node in current_definition.nodes)
            has_filter = any(node.type == "filter" for node in current_definition.nodes)

            lines.append("In your current workflow:")
            lines.append(
                f"- Performance signals: api_calls_per_run~{api_node_count}, expensive_ai_nodes={ai_node_count}, early_filter={str(has_filter).lower()}, early_limit={str(has_early_limit).lower()}."
            )
            for node in focus_nodes[:3]:
                lines.append(f"- {node.label} ({node.id}) type={node.type}")
                incoming = [edge for edge in current_definition.edges if edge.target == node.id][:2]
                outgoing = [edge for edge in current_definition.edges if edge.source == node.id][:2]
                anchor = cls._build_node_anchor_line(
                    node_id=node.id,
                    incoming_edges=incoming,
                    outgoing_edges=outgoing,
                    nodes_by_id=nodes_by_id,
                )
                if anchor:
                    lines.append(f"  placement anchor: {anchor}")
                if node.type == "http_request":
                    lines.append("  tuning: add filter/limit right after this node to cut payload before downstream AI or channels.")
                elif node.type == "ai_agent":
                    lines.append("  tuning: constrain output keys and max_tokens; avoid long free-form outputs if only summary fields are needed.")
                elif node.type in {"telegram", "whatsapp", "send_gmail_message", "slack_send_message", "linkedin"}:
                    lines.append("  tuning: route only required branch to this channel; avoid multi-channel fan-out unless explicitly needed.")
                elif node.type == "merge":
                    lines.append("  tuning: choose merge mode carefully to avoid waiting and extra data reshaping overhead.")

        lines.append("Validation checklist:")
        lines.append("1. Compare before/after median run duration and API call count for the same sample input.")
        lines.append("2. Verify functional output remains identical after optimization changes.")
        lines.append("3. Load-test with small burst runs and confirm no new timeout/rate-limit failures.")
        return "\n".join(lines)

    @classmethod
    def _looks_like_security_pii_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        security_tokens = (
            "security",
            "secure",
            "hardening",
            "harden",
            "pii",
            "personally identifiable",
            "sensitive data",
            "secret",
            "token leak",
            "leak",
            "exposure",
            "redact",
            "mask",
            "encrypt",
            "compliance",
            "gdpr",
            "hipaa",
        )
        action_tokens = (
            "how to",
            "how do i",
            "check",
            "audit",
            "review",
            "prevent",
            "protect",
            "secure",
            "harden",
            "where can",
            "what should",
            "guide",
            "checklist",
        )
        has_security_topic = any(token in lowered for token in security_tokens)
        has_action = any(token in lowered for token in action_tokens)
        return has_security_topic and (has_action or "?" in lowered)

    @classmethod
    def _pick_security_focus_nodes(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> list[Any]:
        if current_definition is None:
            return []

        lowered_prompt = str(prompt or "").lower()
        nodes = list(current_definition.nodes)
        selected: list[Any] = []
        seen_ids: set[str] = set()

        def _append(node: Any) -> None:
            node_id = str(node.id or "").strip()
            if not node_id or node_id in seen_ids:
                return
            seen_ids.add(node_id)
            selected.append(node)

        focus_set = set(node_focus_types)
        for node in nodes:
            if node.type in focus_set and node.type in SECURITY_REVIEW_NODE_TYPES:
                _append(node)

        for node in nodes:
            node_id = str(node.id or "").strip().lower()
            node_label = str(node.label or "").strip().lower()
            if node_id and f" {node_id} " in f" {lowered_prompt} " and node.type in SECURITY_REVIEW_NODE_TYPES:
                _append(node)
                continue
            if node_label and f" {node_label} " in f" {lowered_prompt} " and node.type in SECURITY_REVIEW_NODE_TYPES:
                _append(node)

        preferred_types = (
            "webhook_trigger",
            "http_request",
            "search_update_google_sheets",
            "file_write",
            "send_gmail_message",
            "telegram",
            "whatsapp",
            "slack_send_message",
            "linkedin",
        )
        for preferred_type in preferred_types:
            for node in nodes:
                if node.type == preferred_type:
                    _append(node)
                    if len(selected) >= 5:
                        break
            if len(selected) >= 5:
                break

        return selected[:5]

    @classmethod
    def _build_security_pii_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        focus_nodes = cls._pick_security_focus_nodes(
            prompt=prompt,
            current_definition=current_definition,
            node_focus_types=node_focus_types,
        )

        lines: list[str] = [
            "Direct answer:",
            "- Secure this workflow by hardening secrets handling, minimizing PII movement, and redacting sensitive data from logs and outbound channels.",
            "Security & PII hardening checklist:",
            "1. Keep secrets only in credentials/secure config; never hardcode tokens/passwords in node config or prompts.",
            "2. Minimize PII fields passed downstream (send only required keys to each node/channel).",
            "3. Enforce transport security (`https` endpoints) and avoid writing raw PII to local files unless required.",
            "4. Redact/mask PII in logs, debug payloads, and customer-facing notifications.",
            "5. Add access control and ownership boundaries for sheets/docs/channels receiving customer data.",
            "Recommended hardening changes:",
            "- Add a `code`/`filter` node before outbound nodes to drop unnecessary sensitive fields.",
            "- For webhook/form entries, validate auth + schema early and reject malformed requests quickly.",
            "- Replace direct identifiers in external notifications with ticket_id/reference_id where possible.",
        ]

        if current_definition is not None:
            nodes_by_id = {
                str(node.id or "").strip(): node
                for node in current_definition.nodes
                if str(node.id or "").strip()
            }
            sensitive_config_nodes = 0
            pii_signals: list[str] = []
            seen_signals: set[str] = set()
            outbound_nodes = [
                node
                for node in current_definition.nodes
                if node.type in {"send_gmail_message", "telegram", "whatsapp", "slack_send_message", "linkedin", "http_request"}
            ]

            for node in current_definition.nodes:
                config = node.config if isinstance(node.config, Mapping) else {}
                if any(
                    key in config and str(config.get(key) or "").strip()
                    for key in ASSISTANT_SENSITIVE_CONFIG_KEYS
                ):
                    sensitive_config_nodes += 1

                templates = cls._extract_template_expressions(config)
                for template in templates:
                    lowered_template = str(template or "").lower()
                    if any(hint in lowered_template for hint in SECURITY_PII_FIELD_HINTS):
                        normalized = str(template or "").strip()
                        if normalized and normalized.lower() not in seen_signals:
                            seen_signals.add(normalized.lower())
                            pii_signals.append(normalized)
                    if len(pii_signals) >= 8:
                        break

            lines.append("In your current workflow:")
            lines.append(
                f"- Security posture: sensitive_config_nodes={sensitive_config_nodes}, outbound_nodes={len(outbound_nodes)}, possible_pii_signals={len(pii_signals)}."
            )
            if pii_signals:
                lines.append("- Possible PII signal fields: " + ", ".join(f"`{{{{{item}}}}}`" for item in pii_signals[:6]))
            else:
                lines.append("- Possible PII signal fields: none detected from current template paths.")

            for node in focus_nodes[:3]:
                lines.append(f"- {node.label} ({node.id}) type={node.type}")
                incoming = [edge for edge in current_definition.edges if edge.target == node.id][:2]
                outgoing = [edge for edge in current_definition.edges if edge.source == node.id][:2]
                anchor = cls._build_node_anchor_line(
                    node_id=node.id,
                    incoming_edges=incoming,
                    outgoing_edges=outgoing,
                    nodes_by_id=nodes_by_id,
                )
                if anchor:
                    lines.append(f"  placement anchor: {anchor}")
                if node.type == "http_request":
                    lines.append("  hardening: keep URL on HTTPS, avoid body fields with raw PII unless required, and use credential auth instead of inline tokens.")
                elif node.type in {"send_gmail_message", "telegram", "whatsapp", "slack_send_message", "linkedin"}:
                    lines.append("  hardening: avoid sending full customer identifiers; prefer ticket id + masked contact details.")
                elif node.type in {"search_update_google_sheets", "file_write"}:
                    lines.append("  hardening: store minimal fields and restrict who can access this data sink.")

        lines.append("Validation checklist:")
        lines.append("1. Verify no secrets/tokens appear in exported workflow JSON or runtime logs.")
        lines.append("2. Run one sample and confirm outbound payloads contain only required, minimized fields.")
        lines.append("3. Confirm PII fields are masked/redacted where full values are not necessary.")
        return "\n".join(lines)

    @classmethod
    def _looks_like_publish_ops_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        publish_tokens = (
            "publish",
            "publishing",
            "deploy",
            "deployment",
            "go live",
            "go-live",
            "production checklist",
            "release",
            "rollout",
            "preflight",
            "operations",
            "runbook",
            "launch checklist",
        )
        action_tokens = (
            "checklist",
            "before",
            "ready",
            "readiness",
            "validate",
            "verify",
            "how to",
            "guide",
            "steps",
        )
        debug_bias_tokens = ("failed", "error", "stuck", "waiting", "exception", "status code")

        has_publish_topic = any(token in lowered for token in publish_tokens)
        has_action_signal = any(token in lowered for token in action_tokens)
        has_debug_bias = any(token in lowered for token in debug_bias_tokens)

        if has_debug_bias and not has_publish_topic:
            return False
        return has_publish_topic and (has_action_signal or "?" in lowered)

    @classmethod
    def _pick_publish_focus_nodes(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> list[Any]:
        if current_definition is None:
            return []

        lowered_prompt = str(prompt or "").lower()
        nodes = list(current_definition.nodes)
        selected: list[Any] = []
        seen_ids: set[str] = set()

        def _append(node: Any) -> None:
            node_id = str(node.id or "").strip()
            if not node_id or node_id in seen_ids:
                return
            seen_ids.add(node_id)
            selected.append(node)

        focus_set = set(node_focus_types)
        for node in nodes:
            if node.type in focus_set and node.type in PUBLISH_CRITICAL_NODE_TYPES:
                _append(node)

        for node in nodes:
            node_id = str(node.id or "").strip().lower()
            node_label = str(node.label or "").strip().lower()
            if node_id and f" {node_id} " in f" {lowered_prompt} " and node.type in PUBLISH_CRITICAL_NODE_TYPES:
                _append(node)
                continue
            if node_label and f" {node_label} " in f" {lowered_prompt} " and node.type in PUBLISH_CRITICAL_NODE_TYPES:
                _append(node)

        for node in nodes:
            if node.type in PUBLISH_CRITICAL_NODE_TYPES:
                _append(node)
                if len(selected) >= 4:
                    break

        return selected[:4]

    @classmethod
    def _build_publish_ops_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        focus_nodes = cls._pick_publish_focus_nodes(
            prompt=prompt,
            current_definition=current_definition,
            node_focus_types=node_focus_types,
        )

        lines: list[str] = [
            "Direct answer:",
            "- Before publishing, run a go-live readiness gate across config correctness, failure handling, observability, and rollback safety.",
            "Publish/deploy operations checklist:",
            "1. Validate trigger config + one full dry-run using representative payloads.",
            "2. Verify every external integration credential and endpoint in production environment.",
            "3. Ensure failure paths exist (retry/fallback or explicit stop + alert) for critical outbound nodes.",
            "4. Add run observability fields and operational alerts for failed executions.",
            "5. Document rollback plan: disable trigger, revert latest config, and replay safe test run.",
            "Recommended pre-publish gates:",
            "- Run 3 test cases: happy path, validation failure path, and integration failure path.",
            "- Confirm no node remains in waiting/stuck state for branch-specific runs.",
            "- Ensure sensitive values are stored in credentials, not inline config.",
        ]

        if current_definition is not None:
            nodes_by_id = {
                str(node.id or "").strip(): node
                for node in current_definition.nodes
                if str(node.id or "").strip()
            }
            has_trigger = any(node.type in TRIGGER_NODE_TYPES for node in current_definition.nodes)
            has_routing = any(node.type in {"if_else", "switch"} for node in current_definition.nodes)
            has_delay = any(node.type == "delay" for node in current_definition.nodes)
            has_observability_sink = any(
                node.type in {"search_update_google_sheets", "file_write", "create_google_docs"}
                for node in current_definition.nodes
            )
            outbound_nodes = [
                node
                for node in current_definition.nodes
                if node.type in {"http_request", "send_gmail_message", "telegram", "whatsapp", "slack_send_message", "linkedin"}
            ]
            missing_credential_nodes: list[str] = []
            for node in current_definition.nodes:
                config = node.config if isinstance(node.config, Mapping) else {}
                if "credential_id" not in config:
                    continue
                if str(config.get("credential_id") or "").strip():
                    continue
                if node.type == "http_request" and str(config.get("auth_mode") or "none").strip().lower() == "none":
                    continue
                missing_credential_nodes.append(str(node.id))

            missing_http_url_nodes = [
                str(node.id)
                for node in current_definition.nodes
                if node.type == "http_request"
                and not str((node.config or {}).get("url") or "").strip()
            ]

            lines.append("In your current workflow:")
            lines.append(
                f"- Go-live readiness: trigger={str(has_trigger).lower()}, outbound_nodes={len(outbound_nodes)}, routing_guard={str(has_routing).lower()}, retry_delay={str(has_delay).lower()}, observability={str(has_observability_sink).lower()}."
            )

            blockers: list[str] = []
            if not has_trigger:
                blockers.append("No valid trigger node found.")
            if missing_credential_nodes:
                blockers.append("Missing credential_id on nodes: " + ", ".join(missing_credential_nodes[:5]))
            if missing_http_url_nodes:
                blockers.append("HTTP nodes missing URL: " + ", ".join(missing_http_url_nodes[:5]))
            if not has_observability_sink:
                blockers.append("No persistence/observability sink found (consider sheet/file status logging).")

            if blockers:
                lines.append("Immediate blockers:")
                for blocker in blockers[:4]:
                    lines.append(f"- {blocker}")

            for node in focus_nodes[:3]:
                lines.append(f"- {node.label} ({node.id}) type={node.type}")
                incoming = [edge for edge in current_definition.edges if edge.target == node.id][:2]
                outgoing = [edge for edge in current_definition.edges if edge.source == node.id][:2]
                anchor = cls._build_node_anchor_line(
                    node_id=node.id,
                    incoming_edges=incoming,
                    outgoing_edges=outgoing,
                    nodes_by_id=nodes_by_id,
                )
                if anchor:
                    lines.append(f"  placement anchor: {anchor}")

        lines.append("Validation checklist:")
        lines.append("1. Execute end-to-end dry run with production-like payload and verify all critical nodes succeed.")
        lines.append("2. Simulate one integration failure and verify expected operational behavior (retry/fallback/alert).")
        lines.append("3. Confirm rollback path is documented and trigger can be safely paused.")
        return "\n".join(lines)

    @classmethod
    def _looks_like_n8n_migration_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        migration_tokens = (
            "n8n",
            "n8n-nodes-base",
            "imported flow",
            "imported workflow",
            "migration",
            "migrate",
            "compatibility",
            "translation",
            "convert from n8n",
            "n8n flow failed",
        )
        action_tokens = (
            "what is missing",
            "missing config",
            "missing translation",
            "how to fix",
            "why failed",
            "translate",
            "map node",
            "compatibility check",
            "migration advisor",
        )

        has_migration_topic = any(token in lowered for token in migration_tokens)
        has_action_signal = any(token in lowered for token in action_tokens)
        return has_migration_topic and (has_action_signal or "?" in lowered)

    @classmethod
    def _build_n8n_migration_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        lines: list[str] = [
            "Direct answer:",
            "- Use node-type mapping + expression normalization + routing/merge rewiring to migrate n8n workflows safely.",
            "n8n compatibility/migration advisor:",
            "1. Map n8n node types to Autoflow equivalents before validating configs.",
            "2. Convert n8n expressions (`{{$json...}}`, `$node[...]`) to Autoflow templates (`{{...}}`) and existing upstream field paths.",
            "3. Re-check branch wiring (`if_else`/`switch`) and merge modes after conversion.",
            "4. Rebind credentials for destination nodes after import; do not trust carried credential ids.",
            "Common node translations:",
        ]

        for n8n_type, autoflow_type in list(N8N_NODE_TYPE_EQUIVALENTS.items())[:8]:
            lines.append(f"- `{n8n_type}` -> `{autoflow_type}`")

        if current_definition is None:
            lines.append("What I need to be exact:")
            lines.append("- Imported workflow JSON (or at least node type list + one failing node error).")
            lines.append("Validation checklist:")
            lines.append("1. Confirm each imported node has a mapped Autoflow type.")
            lines.append("2. Confirm templates resolve from upstream output.")
            lines.append("3. Run one dry run and patch unmapped nodes.")
            return "\n".join(lines)

        n8n_like_nodes = [
            node
            for node in current_definition.nodes
            if str(node.type or "").strip().startswith("n8n-") or "n8n-nodes-base." in str(node.type or "").strip()
        ]
        mapped_nodes: list[str] = []
        unknown_n8n_types: list[str] = []
        unsupported_n8n_types: list[str] = []
        seen_unknown: set[str] = set()
        seen_unsupported: set[str] = set()

        for node in n8n_like_nodes:
            node_type = str(node.type or "").strip()
            mapped_to = N8N_NODE_TYPE_EQUIVALENTS.get(node_type)
            if mapped_to:
                mapped_nodes.append(f"{node_type}->{mapped_to}")
            else:
                if node_type not in seen_unknown:
                    seen_unknown.add(node_type)
                    unknown_n8n_types.append(node_type)
            if node_type in N8N_MIGRATION_KNOWN_UNSUPPORTED and node_type not in seen_unsupported:
                seen_unsupported.add(node_type)
                unsupported_n8n_types.append(node_type)

        n8n_expression_signals: list[str] = []
        seen_expressions: set[str] = set()
        for node in current_definition.nodes:
            templates = cls._extract_template_expressions(node.config)
            for expr in templates:
                normalized = str(expr or "").strip()
                lowered_expr = normalized.lower()
                if not normalized:
                    continue
                if "$json" in lowered_expr or "$node[" in lowered_expr or "$binary" in lowered_expr:
                    key = lowered_expr
                    if key in seen_expressions:
                        continue
                    seen_expressions.add(key)
                    n8n_expression_signals.append(normalized)
                    if len(n8n_expression_signals) >= 8:
                        break
            if len(n8n_expression_signals) >= 8:
                break

        risky_merge_nodes = [
            node.id
            for node in current_definition.nodes
            if node.type == "merge"
            and isinstance(node.config, Mapping)
            and str(node.config.get("mode") or "").strip() == "append"
            and int(node.config.get("input_count") or 2) > 1
        ]

        lines.append("In your current workflow:")
        lines.append(
            f"- n8n_like_nodes={len(n8n_like_nodes)}, mapped_types={len(mapped_nodes)}, unmapped_types={len(unknown_n8n_types)}."
        )
        if mapped_nodes:
            lines.append("- Mapped node previews: " + ", ".join(f"`{item}`" for item in mapped_nodes[:6]))
        if n8n_expression_signals:
            lines.append("- n8n expression signals detected: " + ", ".join(f"`{{{{{expr}}}}}`" for expr in n8n_expression_signals[:4]))

        lines.append("Immediate compatibility risks:")
        if unknown_n8n_types:
            lines.append("- Unmapped n8n node types: " + ", ".join(f"`{item}`" for item in unknown_n8n_types[:6]))
        if unsupported_n8n_types:
            lines.append("- Known migration hot-spots requiring manual redesign: " + ", ".join(f"`{item}`" for item in unsupported_n8n_types[:6]))
        if n8n_expression_signals:
            lines.append("- Expression translation required: convert n8n `$json/$node` paths into Autoflow `{{...}}` references.")
        if risky_merge_nodes:
            lines.append("- Merge review needed on node ids: " + ", ".join(f"`{node_id}`" for node_id in risky_merge_nodes[:4]))
        if not any((unknown_n8n_types, unsupported_n8n_types, n8n_expression_signals, risky_merge_nodes)):
            lines.append("- No high-risk migration issue detected from current structure; proceed with dry-run validation.")

        lines.append("Migration steps:")
        lines.append("1. Replace each n8n node type with mapped Autoflow type and copy only supported config keys.")
        lines.append("2. Recreate expressions/templates using upstream node ids and concrete output keys.")
        lines.append("3. Rewire branch edges using explicit `branch` values (`true/false` or switch case ids).")
        lines.append("4. Run one controlled input and patch remaining unsupported nodes with code/filter/split alternatives.")

        if node_focus_types:
            lines.append("Focus nodes from your query:")
            lines.append("- " + ", ".join(f"`{node_type}`" for node_type in node_focus_types[:4]))

        lines.append("Validation checklist:")
        lines.append("1. Confirm zero unmapped node types remain after conversion.")
        lines.append("2. Confirm all templates resolve (no unresolved `$json/$node` style references).")
        lines.append("3. Execute a dry run and verify downstream behavior matches source workflow intent.")
        return "\n".join(lines)

    @classmethod
    def _pick_likely_failing_nodes(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
        error_kind: str,
    ) -> list[Any]:
        if current_definition is None:
            return []

        lowered_prompt = str(prompt or "").lower()
        nodes = list(current_definition.nodes)
        selected: list[Any] = []
        seen_ids: set[str] = set()

        def _append_node(node: Any) -> None:
            node_id = str(node.id or "").strip()
            if not node_id or node_id in seen_ids:
                return
            seen_ids.add(node_id)
            selected.append(node)

        # Priority 1: explicit focus matches.
        if node_focus_types:
            focus_set = set(node_focus_types)
            for node in nodes:
                if node.type in focus_set:
                    _append_node(node)

        # Priority 2: node id/label mentioned in prompt.
        for node in nodes:
            node_id = str(node.id or "").strip().lower()
            node_label = str(node.label or "").strip().lower()
            if node_id and f" {node_id} " in f" {lowered_prompt} ":
                _append_node(node)
                continue
            if node_label and f" {node_label} " in f" {lowered_prompt} ":
                _append_node(node)

        # Priority 3: error-kind based defaults.
        kind_priority: dict[str, tuple[str, ...]] = {
            "not_found": ("http_request",),
            "auth": ("http_request", "send_gmail_message", "create_gmail_draft", "add_gmail_label", "telegram", "whatsapp", "slack_send_message", "linkedin"),
            "payload_validation": ("http_request", "search_update_google_sheets", "send_gmail_message", "create_gmail_draft", "add_gmail_label"),
            "rate_limit": ("http_request", "telegram", "whatsapp", "send_gmail_message", "create_gmail_draft", "add_gmail_label", "slack_send_message", "linkedin"),
            "server_or_gateway": ("http_request",),
            "network_or_timeout": ("http_request",),
            "merge_waiting": ("merge",),
            "branch_condition": ("if_else", "switch", "filter"),
            "template_mapping": ("ai_agent", "code", "send_gmail_message", "create_gmail_draft", "add_gmail_label", "telegram", "whatsapp", "slack_send_message", "linkedin"),
            "generic_runtime": ("code", "ai_agent", "http_request"),
        }
        for preferred_type in kind_priority.get(error_kind, ()):
            for node in nodes:
                if node.type == preferred_type:
                    _append_node(node)

        if not selected:
            for node in nodes:
                if node.type not in TRIGGER_NODE_TYPES and node.type not in AI_CHAT_MODEL_NODE_TYPES:
                    _append_node(node)
                    if len(selected) >= 2:
                        break

        return selected[:3]

    @classmethod
    def _looks_like_credential_oauth_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        credential_tokens = (
            "credential",
            "oauth",
            "access token",
            "refresh token",
            "api key",
            "bearer token",
            "reauthorize",
            "re-authorize",
            "auth",
            "authorization",
            "scope",
            "consent",
            "invalid_grant",
        )
        failure_tokens = (
            "connected but",
            "forbidden",
            "unauthorized",
            "permission denied",
            "insufficient permission",
            "403",
            "401",
            "token expired",
            "token invalid",
            "failed",
            "not working",
            "why fail",
        )
        return any(token in lowered for token in credential_tokens) and any(
            token in lowered for token in failure_tokens
        )

    @classmethod
    def _looks_like_trigger_configuration_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        trigger_tokens = (
            "trigger",
            "schedule",
            "cron",
            "webhook",
            "form trigger",
            "workflow trigger",
            "manual trigger",
        )
        config_tokens = (
            "configure",
            "configuration",
            "config",
            "setup",
            "set up",
            "exact cron",
            "weekday",
            "weekdays",
            "timezone",
            "path",
            "method",
            "rules",
            "9:30",
        )
        best_trigger_only = bool(
            re.search(r"\b(best|which|what)\s+trigger\b", lowered)
        )
        has_trigger = any(token in lowered for token in trigger_tokens)
        has_config = any(token in lowered for token in config_tokens)
        has_time_pattern = bool(
            re.search(r"\b\d{1,2}:\d{2}\s*(am|pm)?\b", lowered)
            or re.search(r"\b\d{1,2}\s*(am|pm)\b", lowered)
        )
        mentions_non_trigger_node = any(
            token in lowered
            for token in (
                "http request",
                "http_request",
                "ai agent",
                "ai_agent",
                "merge",
                "if_else",
                "switch",
                "filter",
                "code node",
                "telegram",
                "gmail",
                "whatsapp",
                "slack",
                "linkedin",
                "google sheets",
                "google docs",
                "image gen",
            )
        )
        return (
            has_trigger
            and (has_config or has_time_pattern)
            and not best_trigger_only
            and not mentions_non_trigger_node
        )

    @classmethod
    def _looks_like_data_mapping_validation_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        check_tokens = ("check", "validate", "verify", "confirm", "cross-check")
        mapping_tokens = (
            "mapping",
            "template field",
            "template fields",
            "template variable",
            "template variables",
            "placeholder",
            "placeholders",
            "upstream output",
            "previous node output",
            "from previous node",
            "field exist",
            "fields exist",
            "resolve template",
            "mapping validator",
        )
        has_check = any(token in lowered for token in check_tokens)
        has_mapping_topic = any(token in lowered for token in mapping_tokens)
        has_template_expression = "{{" in lowered and "}}" in lowered
        return (has_check and has_mapping_topic) or (
            has_template_expression
            and any(token in lowered for token in ("mapping", "template", "previous", "upstream", "exists"))
        )

    @classmethod
    def _looks_like_schema_contract_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        schema_tokens = (
            "json schema",
            "schema",
            "contract",
            "payload shape",
            "input shape",
            "output shape",
            "body should follow",
            "body follow",
            "request body shape",
            "schema check",
            "io shape",
        )
        ask_tokens = ("what", "which", "show", "give", "expected", "should", "follow")
        has_schema = any(token in lowered for token in schema_tokens)
        has_ask = any(token in lowered for token in ask_tokens)
        return has_schema and has_ask

    @classmethod
    def _resolve_schema_focus_node_types(
        cls,
        *,
        prompt: str,
        node_focus_types: list[str],
        current_definition: WorkflowDefinition | None,
    ) -> list[str]:
        focus: list[str] = []
        seen: set[str] = set()

        for node_type in node_focus_types:
            normalized = str(node_type or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            focus.append(normalized)

        lowered = str(prompt or "").lower()
        keyword_map: list[tuple[str, tuple[str, ...]]] = [
            ("http_request", ("http", "api", "request body", "payload", "endpoint", "body_json")),
            ("ai_agent", ("ai agent", "ai_agent", "structured output", "output schema")),
            ("merge", ("merge", "append", "combine", "join")),
            ("if_else", ("if_else", "if else", "condition", "true branch", "false branch")),
            ("switch", ("switch", "case", "default_case")),
            ("code", ("code", "python code", "output dict")),
            ("send_gmail_message", ("email", "gmail", "mail body")),
            ("create_gmail_draft", ("gmail draft", "email draft", "draft email")),
            ("add_gmail_label", ("gmail label", "email label", "label gmail")),
            ("telegram", ("telegram",)),
            ("whatsapp", ("whatsapp", "template_params")),
            ("search_update_google_sheets", ("google sheets", "sheet", "update_mappings")),
            ("form_trigger", ("form", "form trigger", "fields")),
            ("webhook_trigger", ("webhook", "path", "method")),
            ("workflow_trigger", ("workflow trigger", "input_schema", "child workflow")),
        ]
        for node_type, tokens in keyword_map:
            if node_type in seen:
                continue
            if any(token in lowered for token in tokens):
                seen.add(node_type)
                focus.append(node_type)

        if not focus and current_definition is not None:
            for node in current_definition.nodes:
                node_type = str(node.type or "").strip()
                if not node_type or node_type in TRIGGER_NODE_TYPES or node_type in AI_CHAT_MODEL_NODE_TYPES:
                    continue
                if node_type in seen:
                    continue
                seen.add(node_type)
                focus.append(node_type)
                if len(focus) >= 2:
                    break

        if not focus:
            focus.append("http_request")
        return focus[:3]

    @classmethod
    def _render_schema_contract_for_node(
        cls,
        *,
        node_type: str,
        prompt: str,
    ) -> list[str]:
        details = NODE_TYPE_DETAILS.get(node_type, {})
        defaults = NODE_CONFIG_DEFAULTS.get(node_type, {})
        required_hints = cls._build_required_parameter_hints(
            node_type=node_type,
            details=details,
        )

        output_hint_map: dict[str, str] = {
            "http_request": "Output usually includes `status_code`, `headers`, `body`, and optional `response`.",
            "ai_agent": "Output contract is `output.<key>` based on prompt schema (for example `output.summary`).",
            "code": "Return a dict in `output`; downstream templates read from returned keys.",
            "merge": "Output depends on `mode` (`append` gives array under `output_key`; `combine` merges objects).",
            "if_else": "Input payload passes through to either `true` or `false` branch unchanged.",
            "switch": "Input payload passes through to selected case branch.",
            "form_trigger": "Output includes submitted form fields (for example `{{email}}` and `{{form.email}}`).",
            "webhook_trigger": "Output includes inbound request context like `body`, `headers`, and query values.",
            "workflow_trigger": "Output shape follows configured `input_schema` or incoming parent payload.",
            "send_gmail_message": "Output includes send status/metadata after message dispatch.",
            "create_gmail_draft": "Output includes `draft_id` and `created_at` after draft creation.",
            "add_gmail_label": "Output includes `message_id`, `label_id`, `label_name`, and `applied_at`.",
            "telegram": "Output includes delivery response metadata from Telegram API.",
            "whatsapp": "Output includes provider response for template send request.",
            "search_update_google_sheets": "Output includes operation status and row/update response metadata.",
            "image_gen": "Output includes `image_base64`, `image_url`, dimensions, and model metadata.",
        }
        output_hint = output_hint_map.get(
            node_type,
            "Output shape depends on node behavior; validate with one execution output snapshot.",
        )

        lines: list[str] = [
            f"- Node: `{node_type}`",
        ]
        if isinstance(defaults, Mapping):
            config_keys = ", ".join(sorted(defaults.keys()))
            lines.append(f"  config schema keys: {config_keys or 'no config keys'}")
        if required_hints:
            lines.append("  required contract fields:")
            for index, hint in enumerate(required_hints[:4], start=1):
                lines.append(f"  {index}. {hint}")
        lines.append(f"  output contract: {output_hint}")

        if node_type == "http_request":
            schema_starter = {
                "type": "object",
                "additionalProperties": False,
                "required": ["ticket_id", "summary"],
                "properties": {
                    "ticket_id": {"type": "string", "minLength": 1},
                    "summary": {"type": "string", "minLength": 1},
                    "priority": {"type": "string", "enum": ["urgent", "normal"]},
                    "source": {"type": "string"},
                },
            }
            lines.append("  JSON schema starter for `body_json`:")
            lines.append(f"  - `{cls._compact_json(schema_starter, max_chars=420)}`")
            lines.append("  request body example:")
            lines.append(
                "  - `{\"ticket_id\":\"{{ticket_id}}\",\"summary\":\"{{output.summary}}\",\"priority\":\"{{priority}}\"}`"
            )
        elif node_type == "ai_agent":
            output_keys = cls._extract_expected_output_keys(
                str(prompt or ""),
                str(prompt or ""),
            )
            output_schema = {
                "type": "object",
                "required": output_keys[:3] or ["summary"],
                "properties": {key: {"type": "string"} for key in output_keys[:5]},
            }
            lines.append("  output JSON schema starter (under `output`):")
            lines.append(f"  - `{cls._compact_json(output_schema, max_chars=420)}`")
        elif node_type == "workflow_trigger":
            schema_example = {
                "input_data_mode": "fields",
                "input_schema": [
                    {"name": "ticket_id", "type": "String"},
                    {"name": "priority", "type": "String"},
                    {"name": "payload", "type": "Object"},
                ],
            }
            lines.append("  input schema example:")
            lines.append(f"  - `{cls._compact_json(schema_example, max_chars=420)}`")

        return lines

    @classmethod
    def _build_schema_contract_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        focus_types = cls._resolve_schema_focus_node_types(
            prompt=prompt,
            node_focus_types=node_focus_types,
            current_definition=current_definition,
        )

        lines: list[str] = [
            "Direct answer:",
            "- Here is the schema contract guidance for the relevant node(s), including input/config shape and output shape.",
            "Schema contract guidance:",
        ]

        for node_type in focus_types:
            lines.extend(
                cls._render_schema_contract_for_node(
                    node_type=node_type,
                    prompt=prompt,
                )
            )

        if current_definition is not None:
            matched_nodes = [
                node
                for node in current_definition.nodes
                if node.type in set(focus_types)
            ][:4]
            if matched_nodes:
                lines.append("In your current workflow:")
                for node in matched_nodes:
                    lines.append(f"- {node.label} ({node.id}) type={node.type}")
                    config = node.config if isinstance(node.config, Mapping) else {}
                    non_empty_config = {
                        key: value
                        for key, value in config.items()
                        if value not in ("", None, [], {}, False)
                    }
                    if non_empty_config:
                        lines.append(f"  config preview: {cls._compact_json(non_empty_config, max_chars=260)}")

        lines.append("Validation steps:")
        lines.append("1. Compare this contract with the target API/node documentation.")
        lines.append("2. Send one sample run and inspect node input/output in execution logs.")
        lines.append("3. Tighten required fields and enums until runtime validation is stable.")
        return "\n".join(lines)

    @classmethod
    def _looks_like_merge_strategy_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        has_merge = "merge" in lowered
        mode_tokens = (
            "append",
            "combine",
            "combine_by_fields",
            "combine by fields",
            "combine_by_position",
            "combine by position",
            "choose_branch",
            "choose branch",
            "join_type",
            "input_count",
            "which mode",
            "what mode",
            "should i use",
            "merge strategy",
        )
        decision_tokens = (
            "join",
            "fan in",
            "fan-in",
            "combine two inputs",
            "merge case",
            "merge this",
        )
        has_mode_signal = any(token in lowered for token in mode_tokens)
        has_decision_signal = any(token in lowered for token in decision_tokens)
        has_debug_bias = any(
            token in lowered
            for token in ("error", "failed", "waiting", "stuck", "runtime", "not working")
        )
        return has_merge and (has_mode_signal or has_decision_signal) and not (
            has_debug_bias and not has_mode_signal
        )

    @classmethod
    def _resolve_merge_strategy_focus_nodes(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> list[Any]:
        if current_definition is None:
            return []

        lowered = str(prompt or "").lower()
        selected: list[Any] = []
        seen_ids: set[str] = set()

        def _append(node: Any) -> None:
            node_id = str(node.id or "").strip()
            if not node_id or node_id in seen_ids:
                return
            seen_ids.add(node_id)
            selected.append(node)

        if "merge" in set(node_focus_types):
            for node in current_definition.nodes:
                if node.type == "merge":
                    _append(node)

        for node in current_definition.nodes:
            node_id = str(node.id or "").strip().lower()
            node_label = str(node.label or "").strip().lower()
            if node_id and f" {node_id} " in f" {lowered} " and node.type == "merge":
                _append(node)
                continue
            if node_label and f" {node_label} " in f" {lowered} " and node.type == "merge":
                _append(node)

        if not selected:
            for node in current_definition.nodes:
                if node.type == "merge":
                    _append(node)
                    if len(selected) >= 2:
                        break

        return selected[:2]

    @classmethod
    def _infer_merge_mode_recommendation(
        cls,
        *,
        prompt: str,
        merge_node: Any | None = None,
    ) -> tuple[str, str]:
        lowered = str(prompt or "").lower()

        key_join_hint = any(
            token in lowered
            for token in (
                "combine_by_fields",
                "combine by fields",
                "join by",
                "same key",
                "match key",
                "ticket id",
                "ticket_id",
                "email",
                "customer_id",
                "id match",
            )
        )
        position_join_hint = any(
            token in lowered
            for token in (
                "combine_by_position",
                "combine by position",
                "same index",
                "by index",
                "position",
                "row by row",
            )
        )
        choose_branch_hint = any(
            token in lowered
            for token in ("choose_branch", "choose branch", "pick one input", "single input", "input1", "input2")
        )
        append_hint = any(
            token in lowered
            for token in ("append", "concat", "concatenate", "collect", "list", "array")
        )
        combine_hint = any(
            token in lowered
            for token in ("combine", "merge objects", "single object", "overlay")
        )

        if key_join_hint:
            return (
                "combine_by_fields",
                "Use when both inputs have a common key and you want row/object joins (not just concatenation).",
            )
        if position_join_hint:
            return (
                "combine_by_position",
                "Use when input arrays align by index and should be joined item-by-item.",
            )
        if choose_branch_hint:
            return (
                "choose_branch",
                "Use when you intentionally forward exactly one known input handle.",
            )
        if append_hint and not combine_hint:
            return (
                "append",
                "Use when you want to concatenate items from multiple inputs into one list output.",
            )
        if combine_hint:
            return (
                "combine",
                "Use when both inputs are objects and you want one merged object output.",
            )

        if merge_node is not None:
            config = merge_node.config if isinstance(merge_node.config, Mapping) else {}
            existing_mode = str(config.get("mode") or "").strip()
            if existing_mode in {"append", "combine", "combine_by_position", "combine_by_fields", "choose_branch"}:
                return (
                    existing_mode,
                    f"Keep existing `{existing_mode}` mode if it matches your data-shape intent.",
                )

        return (
            "append",
            "Default safe choice for fan-in lists; switch to combine_by_fields only when joining by key.",
        )

    @classmethod
    def _build_merge_strategy_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        merge_nodes = cls._resolve_merge_strategy_focus_nodes(
            prompt=prompt,
            current_definition=current_definition,
            node_focus_types=node_focus_types,
        )
        primary_merge = merge_nodes[0] if merge_nodes else None
        recommended_mode, reason = cls._infer_merge_mode_recommendation(
            prompt=prompt,
            merge_node=primary_merge,
        )

        mode_examples: dict[str, dict[str, Any]] = {
            "append": {"mode": "append", "input_count": 2, "output_key": "merged"},
            "combine": {"mode": "combine", "input_count": 2},
            "combine_by_position": {"mode": "combine_by_position", "input_count": 2, "join_type": "inner"},
            "combine_by_fields": {
                "mode": "combine_by_fields",
                "input_count": 2,
                "input_1_field": "ticket_id",
                "input_2_field": "ticket_id",
                "join_type": "inner",
            },
            "choose_branch": {"mode": "choose_branch", "input_count": 3, "choose_branch": "input1"},
        }

        lines: list[str] = [
            "Direct answer:",
            f"- Recommended merge mode: `{recommended_mode}`.",
            f"- Why: {reason}",
            "Mode chooser:",
            "1. `append`: concatenate inputs into one array (`output_key`).",
            "2. `combine`: merge multiple object inputs into one object.",
            "3. `combine_by_position`: join arrays item-by-item by index.",
            "4. `combine_by_fields`: join by matching keys (`input_1_field`, `input_2_field`).",
            "5. `choose_branch`: forward only one configured input handle.",
        ]

        example = mode_examples.get(recommended_mode)
        if example is not None:
            lines.append("Recommended config example:")
            lines.append(f"- `{cls._compact_json(example, max_chars=340)}`")

        compare_append_vs_fields = "append" in str(prompt or "").lower() and (
            "combine_by_fields" in str(prompt or "").lower()
            or "combine by fields" in str(prompt or "").lower()
        )
        if compare_append_vs_fields:
            lines.append("Append vs combine_by_fields decision:")
            lines.append("- Use `append` when you only need to stack/concatenate results.")
            lines.append("- Use `combine_by_fields` when records must be joined by key (for example `ticket_id`).")

        if current_definition is not None and merge_nodes:
            nodes_by_id = {
                str(node.id or "").strip(): node
                for node in current_definition.nodes
                if str(node.id or "").strip()
            }
            lines.append("In your current workflow:")
            for merge_node in merge_nodes:
                config = merge_node.config if isinstance(merge_node.config, Mapping) else {}
                mode = str(config.get("mode") or "append").strip()
                input_count = config.get("input_count", 2)
                lines.append(
                    f"- {merge_node.label} ({merge_node.id}) mode={mode}, input_count={input_count}"
                )
                incoming_edges = [
                    edge for edge in current_definition.edges if edge.target == merge_node.id
                ]
                if incoming_edges:
                    incoming_refs = []
                    branch_values: list[str] = []
                    source_types: set[str] = set()
                    for edge in incoming_edges[:4]:
                        source_id = str(edge.source or "").strip()
                        source_node = nodes_by_id.get(source_id)
                        source_label = source_node.label if source_node is not None else source_id
                        source_type = str(source_node.type or "").strip() if source_node is not None else ""
                        if source_type:
                            source_types.add(source_type)
                        if str(edge.branch or "").strip():
                            branch_values.append(str(edge.branch))
                        incoming_refs.append(f"{source_label}->{merge_node.id}")
                    lines.append(f"  incoming: {', '.join(incoming_refs)}")
                    exclusive_router = (
                        bool(source_types.intersection({"if_else", "switch"}))
                        and len(set(branch_values)) >= 2
                    )
                    if exclusive_router and mode in {"append", "combine", "combine_by_position", "combine_by_fields"}:
                        lines.append(
                            "  warning: merge may wait on mutually-exclusive branches; prefer direct branch-to-next-node routing or a non-blocking design."
                        )
        elif current_definition is not None:
            lines.append("In your current workflow: no `merge` node found yet.")
            lines.append("Where to place it:")
            lines.append("- Place merge after branch/data-prep nodes and before storage/delivery node that needs unified input.")

        lines.append("Validation checklist:")
        lines.append("1. Run one execution and confirm merge does not stay in waiting state.")
        lines.append("2. Verify merged output shape matches downstream node expectations.")
        lines.append("3. Check `input_count` equals the number of active connected input handles.")
        return "\n".join(lines)

    @classmethod
    def _looks_like_loop_control_prompt(cls, prompt: str) -> bool:
        lowered = str(prompt or "").lower()
        if not lowered:
            return False

        loop_tokens = (
            "loop",
            "infinite",
            "forever",
            "repeat",
            "repeating",
            "split_in",
            "split_out",
            "max_node_executions",
            "max_total_node_executions",
            "loop_control",
            "iteration",
            "recursive",
            "back edge",
            "cycle",
            "cyclic",
        )
        prevention_tokens = (
            "prevent",
            "stop",
            "avoid",
            "control",
            "limit",
            "guard",
            "safeguard",
            "how to",
            "running forever",
            "run forever",
        )
        has_loop_signal = any(token in lowered for token in loop_tokens)
        has_prevention_signal = any(token in lowered for token in prevention_tokens)
        return has_loop_signal and has_prevention_signal

    @classmethod
    def _detect_workflow_cycles(
        cls,
        *,
        definition: WorkflowDefinition | None,
        max_cycles: int = 3,
    ) -> list[list[str]]:
        if definition is None:
            return []

        adjacency: dict[str, list[str]] = {}
        for edge in definition.edges:
            source = str(edge.source or "").strip()
            target = str(edge.target or "").strip()
            if not source or not target:
                continue
            adjacency.setdefault(source, []).append(target)

        visited: set[str] = set()
        stack: list[str] = []
        in_stack: set[str] = set()
        cycles: list[list[str]] = []
        seen_signatures: set[tuple[str, ...]] = set()

        def _dfs(node_id: str) -> bool:
            visited.add(node_id)
            stack.append(node_id)
            in_stack.add(node_id)
            for neighbor in adjacency.get(node_id, []):
                if len(cycles) >= max_cycles:
                    return True
                if neighbor not in visited:
                    if _dfs(neighbor):
                        return True
                    continue
                if neighbor in in_stack:
                    try:
                        start_index = stack.index(neighbor)
                    except ValueError:
                        continue
                    cycle_path = stack[start_index:] + [neighbor]
                    signature = tuple(cycle_path)
                    if signature not in seen_signatures:
                        seen_signatures.add(signature)
                        cycles.append(cycle_path)
                        if len(cycles) >= max_cycles:
                            return True
            in_stack.discard(node_id)
            if stack:
                stack.pop()
            return False

        node_ids = [
            str(node.id or "").strip()
            for node in definition.nodes
            if str(node.id or "").strip()
        ]
        for node_id in node_ids:
            if node_id in visited:
                continue
            if _dfs(node_id):
                break

        return cycles

    @classmethod
    def _build_loop_control_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lines: list[str] = [
            "Direct answer:",
            "- Prevent infinite loops with three controls together: explicit exit condition, bounded loop_control limits, and safe branch design.",
            "Loop prevention strategy:",
            "1. Add an exit guard (`if_else`/`switch`/`filter`) before any back-edge that returns to earlier nodes.",
            "2. Keep `loop_control.enabled=true` and set strict execution caps for loop-heavy workflows.",
            "3. In split loops, close with `split_out` and avoid unconditional edges back into `split_in`.",
            "4. For retry-style loops, add `delay` and max-attempt counter fields so retries terminate.",
            "5. Ensure every loop path has at least one terminal path to final output/storage.",
        ]

        if current_definition is not None:
            nodes_by_id = {
                str(node.id or "").strip(): node
                for node in current_definition.nodes
                if str(node.id or "").strip()
            }
            split_in_nodes = [
                node for node in current_definition.nodes if node.type == "split_in"
            ]
            split_out_nodes = [
                node for node in current_definition.nodes if node.type == "split_out"
            ]
            cycles = cls._detect_workflow_cycles(definition=current_definition, max_cycles=3)

            loop_control = current_definition.loop_control
            lines.append("In your current workflow:")
            lines.append(
                f"- loop_control: enabled={str(loop_control.enabled).lower()}, max_node_executions={loop_control.max_node_executions}, max_total_node_executions={loop_control.max_total_node_executions}"
            )
            lines.append(f"- split nodes: split_in={len(split_in_nodes)}, split_out={len(split_out_nodes)}")

            if cycles:
                lines.append("Detected cycle candidates:")
                for cycle in cycles:
                    rendered = " -> ".join(f"`{node_id}`" for node_id in cycle)
                    lines.append(f"- {rendered}")
                lines.append("Cycle guard recommendation:")
                lines.append("- Add/update a condition before the back-edge so the loop exits after success or max attempts.")
            else:
                lines.append("- No explicit graph cycle detected from current edges.")

            if split_in_nodes and not split_out_nodes:
                lines.append("- warning: `split_in` exists without `split_out`; this can cause uncontrolled iteration paths.")

            if loop_control.max_node_executions > 10 or loop_control.max_total_node_executions > 2000:
                lines.append(
                    "- warning: loop limits are high for safety-first mode; consider lowering while debugging."
                )

            suggested_caps = {
                "enabled": True,
                "max_node_executions": min(5, max(2, loop_control.max_node_executions)),
                "max_total_node_executions": min(800, max(200, loop_control.max_total_node_executions)),
            }
            lines.append("Suggested loop_control baseline:")
            lines.append(f"- `{cls._compact_json(suggested_caps, max_chars=180)}`")

            if split_in_nodes:
                sample_split = split_in_nodes[0]
                outgoing_edges = [
                    edge for edge in current_definition.edges if edge.source == sample_split.id
                ]
                if outgoing_edges:
                    target_ids = [
                        str(edge.target or "").strip()
                        for edge in outgoing_edges[:3]
                        if str(edge.target or "").strip()
                    ]
                    target_labels = [
                        f"{nodes_by_id[target_id].label} ({target_id})"
                        for target_id in target_ids
                        if target_id in nodes_by_id
                    ]
                    if target_labels:
                        lines.append(
                            f"- split flow anchor: `{sample_split.id}` currently routes to {', '.join(target_labels)}"
                        )

        lines.append("Validation checklist:")
        lines.append("1. Run one execution and confirm node execution counts stay within configured limits.")
        lines.append("2. Verify loop exits through terminal branch under normal and failure scenarios.")
        lines.append("3. Confirm no node keeps re-running after exit condition becomes true.")
        lines.append("If needed, share:")
        lines.append("- Node ids forming the suspected loop and one execution trace snippet.")
        return "\n".join(lines)

    @classmethod
    def _extract_template_expressions(cls, value: Any) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()

        def _append(expression: str) -> None:
            normalized = " ".join(str(expression or "").split()).strip()
            if not normalized:
                return
            key = normalized.lower()
            if key in seen:
                return
            seen.add(key)
            results.append(normalized)

        def _walk(item: Any) -> None:
            if isinstance(item, str):
                for match in TEMPLATE_DOUBLE_BRACE_PATTERN.finditer(item):
                    _append(match.group(1))
                return
            if isinstance(item, Mapping):
                for nested_value in item.values():
                    _walk(nested_value)
                return
            if isinstance(item, list):
                for nested_value in item:
                    _walk(nested_value)

        _walk(value)
        return results

    @classmethod
    def _collect_ancestor_nodes(
        cls,
        *,
        definition: WorkflowDefinition | None,
        node_id: str,
        max_depth: int = 6,
    ) -> list[Any]:
        if definition is None:
            return []

        nodes_by_id = {
            str(node.id or "").strip(): node
            for node in definition.nodes
            if str(node.id or "").strip()
        }
        parent_ids_by_target: dict[str, list[str]] = {}
        for edge in definition.edges:
            source_id = str(edge.source or "").strip()
            target_id = str(edge.target or "").strip()
            if not source_id or not target_id:
                continue
            parent_ids_by_target.setdefault(target_id, []).append(source_id)

        start_id = str(node_id or "").strip()
        if not start_id:
            return []

        queue: list[tuple[str, int]] = [(start_id, 0)]
        seen: set[str] = {start_id}
        ordered_ids: list[str] = []
        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for parent_id in parent_ids_by_target.get(current_id, []):
                normalized_parent_id = str(parent_id or "").strip()
                if not normalized_parent_id or normalized_parent_id in seen:
                    continue
                seen.add(normalized_parent_id)
                ordered_ids.append(normalized_parent_id)
                queue.append((normalized_parent_id, depth + 1))

        return [
            nodes_by_id[parent_id]
            for parent_id in ordered_ids
            if parent_id in nodes_by_id
        ]

    @classmethod
    def _infer_available_fields_from_node(
        cls,
        *,
        node: Any,
    ) -> set[str]:
        node_type = str(node.type or "").strip()
        config = node.config if isinstance(node.config, Mapping) else {}
        available: set[str] = set()

        if node_type == "ai_agent":
            available.add("output")
            output_keys = cls._extract_expected_output_keys(
                str(config.get("system_prompt") or ""),
                str(config.get("command") or ""),
            )
            for key in output_keys:
                available.add(f"output.{key}")
        elif node_type == "form_trigger":
            available.add("form")
            fields = config.get("fields")
            if isinstance(fields, list):
                for field in fields:
                    if not isinstance(field, Mapping):
                        continue
                    field_name = str(field.get("name") or "").strip()
                    if not field_name:
                        continue
                    available.add(field_name)
                    available.add(f"form.{field_name}")
        elif node_type == "workflow_trigger":
            available.add("input")
            input_schema = config.get("input_schema")
            if isinstance(input_schema, list):
                for field in input_schema:
                    if not isinstance(field, Mapping):
                        continue
                    field_name = str(field.get("name") or "").strip()
                    if field_name:
                        available.add(field_name)
                        available.add(f"input.{field_name}")
        elif node_type == "webhook_trigger":
            available.update({"body", "headers", "query", "params"})
        elif node_type == "http_request":
            available.update({"body", "status_code", "headers", "response"})
        elif node_type == "image_gen":
            available.update(
                {
                    "image_base64",
                    "image_url",
                    "mime_type",
                    "prompt_used",
                    "revised_prompt",
                    "width",
                    "height",
                    "model",
                }
            )
        elif node_type == "file_read":
            available.update({"content", "text", "json", "lines", "base64", "metadata"})
        elif node_type == "file_write":
            available.update({"success", "file_path"})
        elif node_type in {"read_google_sheets", "search_update_google_sheets"}:
            available.update({"rows", "row", "sheet_name", "status"})
        elif node_type in {"read_google_docs", "create_google_docs", "update_google_docs"}:
            available.update({"document_id", "text", "content", "status"})
        elif node_type in MAPPING_PASSTHROUGH_NODE_TYPES:
            available.add("__passthrough__")

        return available

    @classmethod
    def _pick_mapping_target_nodes(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> list[Any]:
        if current_definition is None:
            return []

        lowered_prompt = str(prompt or "").lower()
        selected: list[Any] = []
        seen_ids: set[str] = set()
        focus_set = set(node_focus_types)

        def _append(node: Any) -> None:
            node_id = str(node.id or "").strip()
            if not node_id or node_id in seen_ids:
                return
            seen_ids.add(node_id)
            selected.append(node)

        for node in current_definition.nodes:
            if node.type in focus_set:
                _append(node)

        for node in current_definition.nodes:
            node_id = str(node.id or "").strip().lower()
            node_label = str(node.label or "").strip().lower()
            if node_id and f" {node_id} " in f" {lowered_prompt} ":
                _append(node)
                continue
            if node_label and f" {node_label} " in f" {lowered_prompt} ":
                _append(node)

        for node in current_definition.nodes:
            templates = cls._extract_template_expressions(node.config)
            if templates:
                _append(node)

        if not selected:
            for node in current_definition.nodes:
                if node.type not in TRIGGER_NODE_TYPES and node.type not in AI_CHAT_MODEL_NODE_TYPES:
                    _append(node)
                    break

        return selected[:3]

    @classmethod
    def _validate_template_expression(
        cls,
        *,
        expression: str,
        ancestor_nodes: list[Any],
    ) -> tuple[str, str]:
        normalized = " ".join(str(expression or "").split()).strip()
        if not normalized:
            return "RISK", "Empty template expression."

        ancestor_ids = {
            str(node.id or "").strip()
            for node in ancestor_nodes
            if str(node.id or "").strip()
        }
        available_union: set[str] = set()
        has_passthrough = False
        for ancestor in ancestor_nodes:
            fields = cls._infer_available_fields_from_node(node=ancestor)
            if "__passthrough__" in fields:
                has_passthrough = True
            available_union.update(field for field in fields if field != "__passthrough__")

        lowered = normalized.lower()
        if lowered == "output":
            ai_upstream = any(node.type == "ai_agent" for node in ancestor_nodes)
            if ai_upstream:
                return "VALID", "Upstream ai_agent exists and exposes `output.*`."
            return "RISK", "No upstream ai_agent found for `output.*` references."

        if lowered.startswith("output."):
            ai_nodes = [node for node in ancestor_nodes if node.type == "ai_agent"]
            if not ai_nodes:
                return "RISK", "No upstream ai_agent found, so `output.<field>` is likely undefined here."
            for ai_node in ai_nodes:
                ai_fields = cls._infer_available_fields_from_node(node=ai_node)
                if lowered in {field.lower() for field in ai_fields}:
                    return "VALID", f"Found `{normalized}` in upstream ai_agent `{ai_node.id}` output hints."
            return "RISK", "Upstream ai_agent exists, but this key is not in declared/known output keys."

        parts = normalized.split(".")
        prefix = parts[0]
        if prefix in ancestor_ids:
            return "VALID", f"References upstream node id `{prefix}` directly."

        if normalized in available_union or prefix in available_union:
            return "VALID", "Field matches known upstream output hints."

        if prefix == "form":
            has_form_upstream = any(node.type == "form_trigger" for node in ancestor_nodes)
            if has_form_upstream:
                return "LIKELY_VALID", "Form trigger exists upstream; verify field name exactly matches form schema."
            return "RISK", "No form trigger found upstream for `form.*` mapping."

        if has_passthrough:
            return "LIKELY_VALID", "Upstream includes pass-through transforms; verify this field exists in runtime payload."

        return "RISK", "Field path not found in upstream node outputs."

    @classmethod
    def _build_data_mapping_validation_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        prompt_templates = cls._extract_template_expressions(prompt)

        if current_definition is None:
            lines: list[str] = [
                "Direct answer:",
                "- I can validate mapping fields, but this request has no current workflow definition attached.",
            ]
            if prompt_templates:
                lines.append("Templates detected in your prompt:")
                for expr in prompt_templates[:8]:
                    lines.append(f"- `{{{{{expr}}}}}`")
            lines.append("What I need to validate exactly:")
            lines.append("1. Target node id/label where these templates are used.")
            lines.append("2. Upstream node output sample (or one execution log snapshot).")
            lines.append("Next action:")
            lines.append("- Share workflow JSON or target node details, and I will return a field-by-field validation report.")
            return "\n".join(lines)

        target_nodes = cls._pick_mapping_target_nodes(
            prompt=prompt,
            current_definition=current_definition,
            node_focus_types=node_focus_types,
        )
        if not target_nodes:
            return (
                "Direct answer:\n"
                "- I could not identify a target node for mapping validation.\n"
                "Next action:\n"
                "- Share the destination node id/label and template fields you want to validate."
            )

        nodes_by_id = {
            str(node.id or "").strip(): node
            for node in current_definition.nodes
            if str(node.id or "").strip()
        }
        edges_by_target: dict[str, list[Any]] = {}
        for edge in current_definition.edges:
            target_id = str(edge.target or "").strip()
            if not target_id:
                continue
            edges_by_target.setdefault(target_id, []).append(edge)

        status_counts = {"VALID": 0, "LIKELY_VALID": 0, "RISK": 0}
        lines: list[str] = [
            "Direct answer:",
            "- I validated template mappings against upstream node outputs for this workflow context.",
            "Mapping validation report:",
        ]

        for target_node in target_nodes:
            target_id = str(target_node.id or "").strip()
            target_templates = cls._extract_template_expressions(target_node.config)
            templates: list[str] = []
            seen_templates: set[str] = set()
            for expr in target_templates + prompt_templates:
                key = str(expr or "").strip().lower()
                if not key or key in seen_templates:
                    continue
                seen_templates.add(key)
                templates.append(str(expr).strip())

            ancestors = cls._collect_ancestor_nodes(
                definition=current_definition,
                node_id=target_id,
                max_depth=6,
            )
            immediate_edges = edges_by_target.get(target_id, [])
            immediate_upstream_labels: list[str] = []
            for edge in immediate_edges:
                source_id = str(edge.source or "").strip()
                source_node = nodes_by_id.get(source_id)
                if source_node is None:
                    continue
                immediate_upstream_labels.append(f"{source_node.label} ({source_node.id})")

            lines.append(
                f"- Target: {target_node.label} ({target_node.id}) type={target_node.type}"
            )
            if immediate_upstream_labels:
                lines.append(f"  immediate upstream: {', '.join(immediate_upstream_labels[:4])}")
            elif ancestors:
                lines.append(
                    "  upstream context: "
                    + ", ".join(
                        f"{node.label} ({node.id})"
                        for node in ancestors[:4]
                    )
                )
            else:
                lines.append("  upstream context: none (this node may be near workflow start).")

            if not templates:
                lines.append("  no template mappings found in this node config.")
                continue

            for index, expression in enumerate(templates[:10], start=1):
                status, reason = cls._validate_template_expression(
                    expression=expression,
                    ancestor_nodes=ancestors,
                )
                if status not in status_counts:
                    status_counts[status] = 0
                status_counts[status] += 1
                lines.append(
                    f"  {index}. `{{{{{expression}}}}}` -> {status}: {reason}"
                )
                if status == "RISK":
                    if expression.startswith("output."):
                        lines.append(
                            "     fix: Add this key in ai_agent JSON output keys, or map an existing `{{output.<key>}}` field."
                        )
                    elif "." in expression:
                        lines.append(
                            "     fix: Use a valid upstream node path (for example `{{upstream_node_id.field}}`) or create the field in a code node."
                        )
                    else:
                        lines.append(
                            "     fix: Verify exact field name from upstream node execution output and update this template."
                        )

        total_checked = sum(status_counts.values())
        lines.append("Summary:")
        lines.append(
            f"- checked={total_checked}, valid={status_counts.get('VALID', 0)}, likely_valid={status_counts.get('LIKELY_VALID', 0)}, risk={status_counts.get('RISK', 0)}"
        )
        lines.append("Validation steps:")
        lines.append("1. Run one sample execution and inspect target node input payload.")
        lines.append("2. Replace any RISK mappings with confirmed upstream keys.")
        lines.append("3. Re-run and confirm no unresolved `{{...}}` placeholders remain.")

        return "\n".join(lines)

    @staticmethod
    def _extract_time_components_from_prompt(prompt: str) -> tuple[int, int] | None:
        lowered = str(prompt or "").lower()
        if not lowered:
            return None

        am_pm_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lowered)
        if am_pm_match:
            hour = int(am_pm_match.group(1))
            minute = int(am_pm_match.group(2) or 0)
            suffix = am_pm_match.group(3)
            hour = hour % 12
            if suffix == "pm":
                hour += 12
            return hour, minute

        twenty_four_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lowered)
        if twenty_four_match:
            return int(twenty_four_match.group(1)), int(twenty_four_match.group(2))
        return None

    @staticmethod
    def _infer_schedule_timezone_from_prompt(prompt: str) -> str:
        lowered = str(prompt or "").lower()
        if "asia/kolkata" in lowered or " india " in f" {lowered} " or " ist " in f" {lowered} ":
            return "Asia/Kolkata"
        if "utc" in lowered or "gmt" in lowered:
            return "UTC"
        if "est" in lowered or "edt" in lowered:
            return "America/New_York"
        if "pst" in lowered or "pdt" in lowered:
            return "America/Los_Angeles"
        return "UTC"

    @staticmethod
    def _infer_cron_day_of_week_from_prompt(prompt: str) -> str:
        lowered = str(prompt or "").lower()
        if "weekday" in lowered:
            return "1-5"
        if "weekend" in lowered:
            return "0,6"

        day_map = {
            "monday": "1",
            "tuesday": "2",
            "wednesday": "3",
            "thursday": "4",
            "friday": "5",
            "saturday": "6",
            "sunday": "0",
        }
        found: list[str] = []
        for day_name, cron_value in day_map.items():
            if day_name in lowered:
                found.append(cron_value)
        if found:
            unique = sorted(set(found), key=lambda value: int(value))
            return ",".join(unique)
        return "*"

    @classmethod
    def _infer_schedule_cron_from_prompt(cls, prompt: str) -> str:
        lowered = str(prompt or "").lower()
        time_parts = cls._extract_time_components_from_prompt(prompt)
        if time_parts is None:
            if "morning" in lowered:
                time_parts = (9, 0)
            elif "afternoon" in lowered:
                time_parts = (14, 0)
            elif "evening" in lowered:
                time_parts = (18, 0)
            elif "night" in lowered:
                time_parts = (21, 0)
            else:
                time_parts = (9, 0)
        hour, minute = time_parts
        day_of_week = cls._infer_cron_day_of_week_from_prompt(prompt)
        return f"{minute} {hour} * * {day_of_week}"

    @classmethod
    def _build_trigger_configuration_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lowered = str(prompt or "").lower()
        inferred_trigger = cls._infer_trigger_type_from_prompt(prompt)
        suggested_trigger = inferred_trigger or cls._infer_default_trigger_from_prompt(
            prompt=prompt,
            inferred_trigger=inferred_trigger,
        ) or "manual_trigger"

        if any(token in lowered for token in ("webhook", "api", "payload", "http")):
            suggested_trigger = "webhook_trigger"
        elif any(token in lowered for token in ("form", "submit", "lead form")):
            suggested_trigger = "form_trigger"
        elif any(token in lowered for token in ("workflow trigger", "child workflow", "sub-workflow")):
            suggested_trigger = "workflow_trigger"
        elif any(token in lowered for token in ("cron", "schedule", "daily", "weekday", "weekdays", "every ")):
            suggested_trigger = "schedule_trigger"

        lines: list[str] = [
            "Direct answer:",
            f"- Trigger configuration assistant: use `{suggested_trigger}` for this request.",
            "Where to place it:",
            "- Trigger must be the first node in the workflow with indegree 0.",
        ]

        if suggested_trigger == "schedule_trigger":
            timezone = cls._infer_schedule_timezone_from_prompt(prompt)
            explicit_rule = cls._extract_schedule_rule_from_prompt(prompt)
            if explicit_rule and str(explicit_rule.get("interval") or "") != "custom":
                config_example = {
                    "timezone": timezone,
                    "enabled": True,
                    "rules": [explicit_rule],
                }
                lines.append("Exact schedule config:")
                lines.append(f"- `{cls._compact_json(config_example, max_chars=420)}`")
                lines.append("Parameters:")
                lines.append("- `timezone`: execution timezone for trigger evaluation.")
                lines.append("- `rules[0].interval` and `rules[0].every`: cadence definition.")
                lines.append("- `rules[0].trigger_hour` / `rules[0].trigger_minute`: run time within the interval.")
            else:
                cron_value = cls._infer_schedule_cron_from_prompt(prompt)
                config_example = {
                    "timezone": timezone,
                    "enabled": True,
                    "rules": [
                        {
                            "id": "rule_1",
                            "interval": "custom",
                            "cron": cron_value,
                            "enabled": True,
                        }
                    ],
                }
                lines.append("Exact cron:")
                lines.append(f"- `{cron_value}`")
                lines.append("Exact schedule config:")
                lines.append(f"- `{cls._compact_json(config_example, max_chars=420)}`")
                lines.append("Parameters:")
                lines.append("- `rules[0].cron`: 5-field cron `minute hour day month weekday`.")
                lines.append("- `timezone`: keep timezone explicit (for IST use `Asia/Kolkata`).")
                lines.append("- `enabled`: set true for active schedules.")

        elif suggested_trigger == "webhook_trigger":
            webhook_config = cls._hydrate_webhook_config_from_prompt(
                NODE_CONFIG_DEFAULTS.get("webhook_trigger", {}),
                prompt,
            )
            lines.append("Exact webhook config:")
            lines.append(f"- `{cls._compact_json(webhook_config, max_chars=320)}`")
            lines.append("Parameters:")
            lines.append("- `path`: incoming endpoint path (without base domain).")
            lines.append("- `method`: HTTP method expected from sender.")
            lines.append("- Send requests from client/Postman to this webhook URL + path.")

        elif suggested_trigger == "form_trigger":
            form_config = cls._hydrate_form_config_from_prompt(
                NODE_CONFIG_DEFAULTS.get("form_trigger", {}),
                prompt,
            )
            lines.append("Exact form config:")
            lines.append(f"- `{cls._compact_json(form_config, max_chars=420)}`")
            lines.append("Parameters:")
            lines.append("- `form_title`, `form_description`: user-facing form metadata.")
            lines.append("- `fields`: input schema (name, label, type, required).")
            lines.append("- Keep at least one required identifier field such as `email`.")

        elif suggested_trigger == "workflow_trigger":
            workflow_config = deepcopy(NODE_CONFIG_DEFAULTS.get("workflow_trigger", {}))
            lines.append("Exact workflow trigger config:")
            lines.append(f"- `{cls._compact_json(workflow_config, max_chars=420)}`")
            lines.append("Parameters:")
            lines.append("- `input_data_mode`: choose `fields`, `json_example`, or `accept_all`.")
            lines.append("- `input_schema`: declare expected keys when mode=`fields`.")
            lines.append("- This trigger is only for child workflows called by `execute_workflow`.")

        else:
            lines.append("Exact manual trigger config:")
            lines.append("- `{}`")
            lines.append("Parameters:")
            lines.append("- Manual trigger has no required config keys.")

        if current_definition is not None:
            trigger_nodes = [node for node in current_definition.nodes if node.type in TRIGGER_NODE_TYPES]
            if trigger_nodes:
                current_trigger = trigger_nodes[0]
                lines.append("In your current workflow:")
                lines.append(f"- Current trigger is `{current_trigger.type}` ({current_trigger.id}).")
                if current_trigger.type != suggested_trigger:
                    lines.append(
                        f"- Replace current trigger with `{suggested_trigger}` only if your input source changed."
                    )

        lines.append("Implementation steps:")
        lines.append("1. Add/keep this trigger as the first node.")
        lines.append("2. Configure trigger parameters exactly as above.")
        lines.append("3. Connect trigger output to the first processing node (http/code/ai/filter).")
        lines.append("4. Run one sample execution and verify trigger payload shape in node output.")
        return "\n".join(lines)

    @classmethod
    def _pick_credential_focus_nodes(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> list[Any]:
        if current_definition is None:
            return []

        lowered_prompt = str(prompt or "").lower()
        nodes = list(current_definition.nodes)
        selected: list[Any] = []
        seen_ids: set[str] = set()

        def _append(node: Any) -> None:
            node_id = str(node.id or "").strip()
            if not node_id or node_id in seen_ids:
                return
            seen_ids.add(node_id)
            selected.append(node)

        focus_set = set(node_focus_types)
        for node in nodes:
            if node.type in focus_set and node.type in CREDENTIAL_TROUBLESHOOT_NODE_TYPES:
                _append(node)

        for node in nodes:
            node_id = str(node.id or "").strip().lower()
            node_label = str(node.label or "").strip().lower()
            if node_id and f" {node_id} " in f" {lowered_prompt} ":
                _append(node)
                continue
            if node_label and f" {node_label} " in f" {lowered_prompt} ":
                _append(node)

        for node in nodes:
            config = node.config if isinstance(node.config, Mapping) else {}
            has_credential_key = "credential_id" in config
            has_http_auth = node.type == "http_request" and str(config.get("auth_mode") or "none").strip().lower() != "none"
            if has_credential_key or has_http_auth:
                _append(node)

        for node in nodes:
            if node.type in CREDENTIAL_TROUBLESHOOT_NODE_TYPES:
                _append(node)
                if len(selected) >= 4:
                    break

        return selected[:4]

    @classmethod
    def _build_credential_oauth_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
        node_focus_types: list[str],
    ) -> str:
        signature = cls._classify_error_signature(prompt)
        status_code = signature.get("status_code")
        auth_failure = bool(
            signature.get("kind") == "auth"
            or status_code in {401, 403}
            or any(
                token in str(prompt or "").lower()
                for token in ("unauthorized", "forbidden", "permission denied")
            )
        )
        focused_nodes = cls._pick_credential_focus_nodes(
            prompt=prompt,
            current_definition=current_definition,
            node_focus_types=node_focus_types,
        )

        scope_hint_by_type: dict[str, str] = {
            "search_update_google_sheets": "Verify Sheets/Drive scopes and share target spreadsheet with the credential owner account.",
            "read_google_sheets": "Verify Sheets/Drive scopes and spreadsheet access for the connected account.",
            "create_google_sheets": "Verify Sheets/Drive scopes and Google Workspace policy permissions.",
            "create_google_docs": "Verify Docs/Drive scopes and document creation permission for the connected account.",
            "read_google_docs": "Verify Docs/Drive scopes and document read access.",
            "update_google_docs": "Verify Docs/Drive scopes and edit permissions on target document.",
            "get_gmail_message": "Verify Gmail read scope and account mailbox access.",
            "send_gmail_message": "Verify Gmail send scope and sender account permission.",
            "linkedin": "Re-authorize LinkedIn credential and confirm post permission scopes are granted.",
            "slack_send_message": "Verify Slack credential/webhook channel permission and app installation.",
            "telegram": "Confirm bot token and destination chat access in Telegram credential.",
            "whatsapp": "Confirm WhatsApp token validity, approved template, and phone-number permissions.",
            "http_request": "Match auth_mode and headers with API docs (Bearer/API key/basic) and verify token/key is active.",
            "chat_model_openai": "Verify API key validity, project access, and model permission.",
            "chat_model_groq": "Verify API key validity and model access permissions.",
            "image_gen": "Verify API key validity and image model entitlement.",
        }

        lines: list[str] = [
            "Direct answer:",
            "- This is a credential/OAuth troubleshooting case. The workflow logic may be correct, but auth binding, token, scope, or account permission is likely wrong.",
        ]
        if auth_failure:
            lines.append("- 401/403 style failures usually mean token/scope/account access mismatch, not node wiring.")
        if status_code is not None:
            lines.append(f"- Detected status code: {status_code}.")

        lines.append("Credential checks to run first:")
        lines.append("1. Open failing node and confirm the correct `credential_id` is selected (not empty, not wrong app/account).")
        lines.append("2. Reconnect OAuth credential to refresh token/consent, then retry the same node with one sample payload.")
        lines.append("3. Verify required scopes for that API and ensure target resource is shared with the connected account.")
        lines.append("4. For `http_request`, verify `auth_mode`, auth header format, and key/token placement exactly match provider docs.")

        if focused_nodes:
            lines.append("In your current workflow:")
            for node in focused_nodes[:4]:
                config = node.config if isinstance(node.config, Mapping) else {}
                credential_id = str(config.get("credential_id") or "").strip()
                credential_state = "set" if credential_id else "missing"
                base_line = f"- {node.label} ({node.id}) type={node.type}, credential_id={credential_state}"
                if node.type == "http_request":
                    auth_mode = str(config.get("auth_mode") or "none").strip().lower()
                    base_line += f", auth_mode={auth_mode}"
                lines.append(base_line)
                scope_hint = scope_hint_by_type.get(node.type)
                if scope_hint:
                    lines.append(f"  fix focus: {scope_hint}")

            missing_credentials = [
                node.id
                for node in focused_nodes
                if not str((node.config or {}).get("credential_id") or "").strip()
                and node.type != "http_request"
            ]
            if missing_credentials:
                lines.append("Immediate blockers:")
                lines.append(f"- Missing credential_id on node(s): {', '.join(missing_credentials)}")

        lines.append("Validation checklist:")
        lines.append("1. Node test passes with one controlled payload.")
        lines.append("2. Error changes from auth/scope to success (or to a non-auth payload error).")
        lines.append("3. Full workflow run reaches downstream node without new credential failures.")
        lines.append("If it still fails, share:")
        lines.append("- Failing node id + exact provider response body (redacted).")
        lines.append("- Which credential/account is connected and what scopes are granted.")

        return "\n".join(lines)

    @classmethod
    def _build_ask_capabilities_response(
        cls,
        *,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lines: list[str] = [
            "Direct answer:",
            "- Ask mode can guide create, edit, add/remove nodes, parameter setup, routing, and runtime error troubleshooting across all Autoflow node types.",
            "Ask mode capabilities:",
            "1. Workflow creation plan: exact node sequence, trigger choice, and edge wiring.",
            "2. Workflow edits: where to insert/remove/replace nodes without breaking existing logic.",
            "3. Node-level help: parameter meaning, correct value format, and template mapping.",
            "4. Data mapping validator: verify `{{...}}` template fields against upstream node outputs.",
            "5. Schema contract checks: expected input/config/output shape per node (including JSON schema starters).",
            "6. Merge strategy advisor: choose append/combine/combine_by_fields/combine_by_position/choose_branch by data shape.",
            "7. Loop control advisor: prevent infinite loops with exit guards and loop_control limits.",
            "8. Execution-log debugging: parse run id/node id, identify failing edge candidates, and provide directed fixes.",
            "9. Reliability design patterns: add safe retry/backoff/fallback/idempotency for outbound and storage paths.",
            "10. Performance/scaling optimization: reduce runtime, API calls, and cost with node-level tuning guidance.",
            "11. Security/PII hardening checks: detect secret exposure risk and provide concrete data-minimization guidance.",
            "12. Publish/deploy operations guidance: go-live checklist, blockers, and rollback readiness checks.",
            "13. n8n compatibility/migration advisor: map imported n8n nodes/expressions and identify translation gaps.",
            "14. Runtime debugging: likely root cause, targeted fix steps, and validation checklist.",
            "15. Trigger configuration assistant: exact cron/webhook/form/workflow trigger setup with concrete parameters.",
            "16. Credential/OAuth troubleshooting: diagnose 401/403, scope mismatch, token refresh, and node-level auth setup.",
            "17. Optimization: simplify complex flows, add retries/fallbacks, and improve observability.",
            "18. Multi-turn continuity: uses accepted workflow context, referenced nodes, and unresolved question memory.",
            "19. Prompt/content quality: improve ai_agent prompts and outbound message formatting.",
            "Supported ask examples:",
            "- `Explain sort node and required parameters.`",
            "- `Check if these template fields exist from previous node output.`",
            "- `What JSON schema should http_request body follow for this API?`",
            "- `Should I use append or combine_by_fields in this merge case?`",
            "- `How to stop this split/merge loop from running forever?`",
            "- `Analyze execution run id 8f2ab91 and node id sync_ticket_http, tell exact failing edge and fix.`",
            "- `How do I add safe retry + fallback for WhatsApp failure with idempotency?`",
            "- `How to reduce runtime and API calls for this 12-node workflow?`",
            "- `Where can this workflow leak secrets/PII and how to secure it?`",
            "- `Checklist before publishing this workflow to production?`",
            "- `This imported n8n flow failed; what config translation is missing?`",
            "- `Where should I place limit node in this flow?`",
            "- `I get 422 in http_request, how to fix?`",
            "- `Give me exact cron for weekdays 9:30 AM IST.`",
            "- `Google Sheets credential is connected but node fails 403, how to fix?`",
            "- `Best trigger for incoming API payloads?`",
            "Scope note:",
            "- Build mode applies structural generation/modification. Ask mode provides directed guidance for all nodes and workflow-level decisions.",
            "Current limits:",
            "- Full workflow JSON generation belongs to Build mode unless user explicitly asks JSON in Ask mode.",
            "- Precise debugging may still need failing node id + exact error line + sample payload.",
        ]
        if current_definition is not None:
            lines.append("In your current workflow:")
            lines.append(
                f"- Context loaded with {len(current_definition.nodes)} nodes and {len(current_definition.edges)} edges."
            )
        return "\n".join(lines)

    @classmethod
    def _build_general_workflow_qa_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lowered = str(prompt or "").lower()
        inferred_trigger = cls._infer_trigger_type_from_prompt(prompt)
        suggested_trigger = inferred_trigger or cls._infer_default_trigger_from_prompt(
            prompt=prompt,
            inferred_trigger=inferred_trigger,
        ) or "manual_trigger"
        if any(token in lowered for token in ("webhook", "api", "payload", "incoming event", "http")):
            suggested_trigger = "webhook_trigger"
        elif any(token in lowered for token in ("form", "submit", "submission")):
            suggested_trigger = "form_trigger"
        elif any(token in lowered for token in ("daily", "weekly", "hourly", "schedule", "cron", "every ")):
            suggested_trigger = "schedule_trigger"

        reason_map: dict[str, str] = {
            "webhook_trigger": "best for API/incoming event payloads from external systems.",
            "form_trigger": "best for user-submitted forms and structured lead capture.",
            "schedule_trigger": "best for recurring jobs (daily/weekly/hourly).",
            "workflow_trigger": "best when this flow should be called by another workflow.",
            "manual_trigger": "best for on-demand tests or ad-hoc runs only.",
        }
        reason = reason_map.get(
            suggested_trigger,
            "best match based on prompt intent and execution style.",
        )

        lines: list[str] = [
            "Direct answer:",
            f"- Recommended trigger: `{suggested_trigger}` ({reason})",
            "Quick selection guide:",
            "1. `webhook_trigger`: external API/event payloads.",
            "2. `form_trigger`: form submissions from users.",
            "3. `schedule_trigger`: time-based automation.",
            "4. `workflow_trigger`: parent-child workflow orchestration.",
            "5. `manual_trigger`: only for testing/manual runs.",
        ]

        if "api" in lowered or "payload" in lowered or "webhook" in lowered:
            lines.append("Starter config (example):")
            lines.append("- `webhook_trigger`: `{ \"path\": \"inbound/events\", \"method\": \"POST\" }`")
        if any(token in lowered for token in ("daily", "weekly", "schedule", "every")):
            lines.append("Starter config (example):")
            lines.append("- `schedule_trigger`: set `rules[0].interval`, `trigger_hour`, and `trigger_minute`.")

        if current_definition is not None:
            trigger_nodes = [node for node in current_definition.nodes if node.type in TRIGGER_NODE_TYPES]
            if trigger_nodes:
                current_trigger = trigger_nodes[0]
                lines.append("In your current workflow:")
                lines.append(f"- Current trigger is `{current_trigger.type}` ({current_trigger.id}).")
                if current_trigger.type != suggested_trigger:
                    lines.append(
                        f"- If your use case changed, consider replacing `{current_trigger.type}` with `{suggested_trigger}`."
                    )
        return "\n".join(lines)

    @classmethod
    def _build_workflow_sequence_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lowered = str(prompt or "").lower()
        inferred_trigger = cls._infer_trigger_type_from_prompt(prompt) or cls._infer_default_trigger_from_prompt(
            prompt=prompt,
            inferred_trigger=None,
        ) or "manual_trigger"
        schedule_language_present = any(
            token in lowered
            for token in (
                "every day",
                "everyday",
                "daily",
                "each day",
                "every morning",
                "morning",
                "weekday",
                "every week",
            )
        ) or bool(re.search(r"\b\d+\s*day(?:s)?\b", lowered))
        if schedule_language_present:
            inferred_trigger = "schedule_trigger"

        sequence: list[str] = [inferred_trigger]

        if any(token in lowered for token in ("api", "newsapi", "fetch", "website", "http")):
            sequence.append("http_request")
        if any(token in lowered for token in ("filter", "related", "keyword")):
            sequence.append("filter")
        if bool(re.search(r"\btop\s*\d+\b", lowered)):
            sequence.append("code")
        if any(token in lowered for token in ("summary", "summarize", "summarise", "digest")):
            sequence.append("ai_agent")

        explicit_channels: list[str] = []
        if "telegram" in lowered:
            explicit_channels.append("telegram")
        if any(token in lowered for token in ("whatsapp", "watsapp", "whats app")):
            explicit_channels.append("whatsapp")
        if any(token in lowered for token in ("gmail label", "email label", "label gmail", "label email")):
            explicit_channels.append("add_gmail_label")
        elif any(token in lowered for token in ("gmail draft", "email draft", "draft email")):
            explicit_channels.append("create_gmail_draft")
        elif any(token in lowered for token in ("gmail", "email", "mail")):
            explicit_channels.append("send_gmail_message")
        if "slack" in lowered:
            explicit_channels.append("slack_send_message")
        if any(token in lowered for token in ("linkedin", "likendin", "linkedin post")):
            explicit_channels.append("linkedin")

        inferred_focus_channels = [
            node_type
            for node_type in cls._resolve_node_focuses_from_prompt(
                lowered,
                current_definition=current_definition,
                max_matches=8,
            )
            if node_type in {"telegram", "whatsapp", "send_gmail_message", "slack_send_message", "linkedin"}
        ]
        requested_channels: list[str] = []
        for channel in [*explicit_channels, *inferred_focus_channels]:
            if channel not in requested_channels:
                requested_channels.append(channel)

        if len(requested_channels) >= 2 and "ai_agent" not in sequence:
            # Multi-channel nurture flows usually need centralized AI personalization before fanout.
            sequence.append("ai_agent")
        for channel_type in requested_channels:
            sequence.append(channel_type)

        deduped: list[str] = []
        seen: set[str] = set()
        for node_type in sequence:
            if node_type in seen:
                continue
            seen.add(node_type)
            deduped.append(node_type)

        lines: list[str] = [
            "Direct answer:",
            "- Yes, this workflow is valid and this is the recommended sequence.",
            "Implementation Steps:",
        ]
        for index, node_type in enumerate(deduped, start=1):
            lines.append(f"{index}. Add `{node_type}`.")

        rendered_sequence = " -> ".join(f"`{node}`" for node in deduped)
        lines.append("Nodes in sequence:")
        lines.append(f"- {rendered_sequence}")
        lines.append("Connection notes:")
        lines.append("- Main edges should follow the sequence above from left to right.")
        if "ai_agent" in deduped:
            lines.append("- Add one `chat_model_openai` (or `chat_model_groq`) node and connect it to `ai_agent` with targetHandle `chat_model`.")
        if "telegram" in deduped:
            lines.append("- Use `{{output.summary}}` from ai_agent in Telegram message.")
        lines.append("Why this order:")
        for node_type in deduped[:8]:
            lines.append(f"- `{node_type}`: {cls._sequence_node_reason(node_type)}")
        if inferred_trigger == "schedule_trigger":
            lines.append("Key schedule parameters:")
            lines.append("- `rules[0].interval`: `days`")
            lines.append("- `rules[0].hour`: e.g. `8` for morning run")
            lines.append("- `rules[0].minute`: e.g. `0`")
        if "http_request" in deduped and "newsapi" in lowered:
            lines.append("Key HTTP parameters for News API:")
            lines.append("- `method`: `GET`")
            lines.append("- `url`: `https://newsapi.org/v2/everything?q=AI OR ML OR Technology OR Space&sortBy=publishedAt&pageSize=50`")
            lines.append("- `auth_mode`: use API key (header) as required by your NewsAPI plan")
        if "code" in deduped:
            lines.append("Top-N preparation:")
            lines.append("- In `code` node, sort news by publish time/relevance and keep first 10 items.")

        if current_definition is not None:
            lines.append("In your current workflow:")
            lines.append(f"- Existing nodes: {len(current_definition.nodes)}, edges: {len(current_definition.edges)}")
            lines.append("- Add this sequence as a new branch or replace the current main path if this is a new requirement.")

        return "\n".join(lines)

    @classmethod
    def _sequence_node_reason(
        cls,
        node_type: str,
    ) -> str:
        reasons: dict[str, str] = {
            "manual_trigger": "Start workflow manually for test/on-demand runs.",
            "form_trigger": "Capture structured user input at entry.",
            "webhook_trigger": "Receive external events/payloads as workflow input.",
            "schedule_trigger": "Run automatically at fixed intervals.",
            "http_request": "Fetch or push data with external APIs.",
            "file_read": "Load local file content before processing.",
            "read_google_sheets": "Read tabular data for downstream processing.",
            "read_google_docs": "Pull document content for summarization/classification.",
            "filter": "Keep only records that match criteria.",
            "sort": "Order records before selection or aggregation.",
            "limit": "Select top-N subset for concise downstream output.",
            "code": "Normalize/transform payload into required shape.",
            "ai_agent": "Generate analysis or structured AI output.",
            "if_else": "Split into two explicit logic branches.",
            "switch": "Route into multiple category-based branches.",
            "merge": "Join multiple branches back into one path.",
            "search_update_google_sheets": "Persist status/results into sheet storage.",
            "file_write": "Store final payload locally for sync/audit.",
            "send_gmail_message": "Deliver final content through email.",
            "create_gmail_draft": "Prepare an email draft without sending it.",
            "add_gmail_label": "Mark an existing Gmail message with a label.",
            "telegram": "Deliver final content through Telegram.",
            "whatsapp": "Deliver final content through WhatsApp.",
            "slack_send_message": "Deliver final content through Slack.",
            "linkedin": "Publish final content to LinkedIn.",
        }
        return reasons.get(
            node_type,
            "Place this where its input dependencies are ready and before its target outputs.",
        )

    @classmethod
    def _build_email_format_improvement_response(
        cls,
        *,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lines: list[str] = [
            "Direct answer:",
            "- Improve email quality by using a fixed structure, shorter sections, and clearer subject/body formatting.",
            "Email formatting improvements:",
            "1. Use subject pattern: `[{{priority}}] Ticket {{ticket_id}} - {{short_topic}}`",
            "2. Keep body in sections: Summary, Impact, Action Taken, Next Step.",
            "3. Use 3-6 bullet points for readability.",
            "4. Add one CTA line: `Reply with logs/screenshots for faster resolution.`",
            "5. Keep max 120-160 words for alert emails.",
            "Template (plain text):",
            "- Subject: [{{priority}}] Ticket {{ticket_id}} - {{short_topic}}",
            "- Body: `Hi {{name}},\\n\\nSummary: {{output.summary}}\\nImpact: {{impact}}\\nNext Step: {{output.recommended_action}}\\n\\nThanks,\\nSupport Team`",
            "Template (HTML, when `is_html=true`):",
            "- `<h3>Ticket {{ticket_id}}</h3><p><strong>Summary:</strong> {{output.summary}}</p><p><strong>Next Step:</strong> {{output.recommended_action}}</p>`",
        ]

        if current_definition is not None:
            mail_nodes = [
                node for node in current_definition.nodes if node.type == "send_gmail_message"
            ]
            if mail_nodes:
                lines.append("In your current workflow:")
                for node in mail_nodes[:3]:
                    config = node.config if isinstance(node.config, Mapping) else {}
                    is_html = bool(config.get("is_html", False))
                    subject = str(config.get("subject") or "").strip()
                    body = str(config.get("body") or "").strip()
                    lines.append(f"- `{node.label}` ({node.id}) is your email node. Update `subject` and `body` there.")
                    lines.append(f"  current is_html={str(is_html).lower()}, subject_len={len(subject)}, body_len={len(body)}")
                    if subject and "{{ticket_id}}" not in subject:
                        lines.append("  suggestion: include `{{ticket_id}}` in subject for better ticket traceability.")
                    if not is_html:
                        lines.append("  suggestion: keep plain text body with short sections and bullet points.")
                    else:
                        lines.append("  suggestion: use simple HTML blocks only (avoid heavy styling for deliverability).")
                lines.append("Validation checklist:")
                lines.append("1. Send one test email to yourself and verify formatting on mobile + desktop.")
                lines.append("2. Confirm all template placeholders resolve (no raw `{{...}}` in final mail).")
                lines.append("3. Keep subject under ~70 chars for better inbox visibility.")
        return "\n".join(lines)

    @classmethod
    def _build_prompt_improvement_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lines: list[str] = [
            "Direct answer:",
            "- Your prompt can be improved by making output format, constraints, and tone explicit.",
            "Good prompt structure:",
            "1. Role: what assistant should act as.",
            "2. Task: exact objective in one line.",
            "3. Constraints: max length, style, must/avoid.",
            "4. Output schema: exact keys or sections required.",
            "Prompt examples:",
            "- `You are a support email assistant. Summarize ticket in <=80 words, professional tone, and return plain text with sections: Summary, Priority, Next Step.`",
            "- `Analyze the input ticket and return JSON only with keys: summary, priority, recommended_action, confidence_score.`",
        ]

        if current_definition is not None:
            ai_nodes = [node for node in current_definition.nodes if node.type == "ai_agent"]
            if ai_nodes:
                lines.append("In your current workflow:")
                for node in ai_nodes[:2]:
                    lines.append(f"- Update `system_prompt` and `command` in `{node.label}` ({node.id}) with the structure above.")
                    config = node.config if isinstance(node.config, Mapping) else {}
                    improved_system, improved_command, output_keys = cls._build_ai_prompt_rewrite(
                        node_config=config
                    )
                    lines.append(f"Suggested replacement for `{node.id}`:")
                    lines.append("system_prompt:")
                    lines.append(f"- `{improved_system}`")
                    lines.append("command:")
                    lines.append(f"- `{improved_command}`")
                    lines.append(
                        "- Downstream template mapping: "
                        + ", ".join(f"`{{{{output.{key}}}}}`" for key in output_keys[:4])
                    )
            else:
                lines.append("Next action:")
                lines.append("- Add one `ai_agent` node, then I can generate exact `system_prompt` and `command` for your use case.")
        else:
            lines.append("Next action:")
            lines.append("- Share your ai_agent goal and expected output keys; I will draft exact `system_prompt` + `command`.")
        return "\n".join(lines)

    @classmethod
    def _build_ai_prompt_rewrite(
        cls,
        *,
        node_config: Mapping[str, Any],
    ) -> tuple[str, str, list[str]]:
        current_system = " ".join(str(node_config.get("system_prompt") or "").split()).strip()
        current_command = " ".join(str(node_config.get("command") or "").split()).strip()

        output_keys = cls._extract_expected_output_keys(current_system, current_command)
        key_list = ", ".join(output_keys)

        role_line = current_system or "You are an Autoflow AI assistant for production workflows."
        if "json" not in role_line.lower():
            role_line = role_line.rstrip(".") + ". Return strict JSON only."
        if "strict json" not in role_line.lower():
            role_line = role_line.rstrip(".") + " Use deterministic, schema-safe outputs."

        command_line = current_command or "Analyze the provided workflow payload and produce actionable output."
        if "return" not in command_line.lower() or "json" not in command_line.lower():
            command_line = (
                f"{command_line.rstrip('.')} Return JSON only with keys: {key_list}."
            )
        elif "keys" not in command_line.lower():
            command_line = (
                f"{command_line.rstrip('.')} Ensure JSON includes keys: {key_list}."
            )

        return role_line, command_line, output_keys

    @classmethod
    def _extract_expected_output_keys(
        cls,
        system_prompt: str,
        command: str,
    ) -> list[str]:
        combined = f"{system_prompt}\n{command}"
        lowered = combined.lower()
        parsed: list[str] = []

        keys_fragment_match = re.search(
            r"keys?\s*[:\-]\s*([a-z0-9_,\s]+)",
            lowered,
            flags=re.IGNORECASE,
        )
        if keys_fragment_match:
            fragment = str(keys_fragment_match.group(1) or "")
            for token in fragment.replace("\n", " ").split(","):
                candidate = re.sub(r"[^a-z0-9_]", "", token.strip().lower())
                if candidate and len(candidate) >= 3:
                    parsed.append(candidate)

        for known in AI_AGENT_STRUCTURED_OUTPUT_KEYS:
            if known in lowered:
                parsed.append(known)

        if not parsed:
            parsed = ["summary", "recommended_action", "confidence_score"]

        ordered: list[str] = []
        seen: set[str] = set()
        for key in parsed:
            normalized = str(key or "").strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered[:8]

    @classmethod
    def _infer_node_focus_from_prompt(
        cls,
        lowered_prompt: str,
        *,
        current_definition: WorkflowDefinition | None = None,
    ) -> str | None:
        focuses = cls._resolve_node_focuses_from_prompt(
            lowered_prompt,
            current_definition=current_definition,
            max_matches=1,
        )
        return focuses[0] if focuses else None

    @classmethod
    def _resolve_node_focuses_from_prompt(
        cls,
        lowered_prompt: str,
        *,
        current_definition: WorkflowDefinition | None = None,
        max_matches: int = 3,
    ) -> list[str]:
        prompt_raw = f" {lowered_prompt} "
        prompt_normalized = " " + re.sub(r"[^a-z0-9_]+", " ", lowered_prompt).strip() + " "
        ordered_hits: list[str] = []

        def _append_unique(node_type: str) -> None:
            normalized = str(node_type or "").strip()
            if not normalized:
                return
            if normalized in ordered_hits:
                return
            ordered_hits.append(normalized)

        def _contains_alias(alias: str) -> bool:
            clean_alias = str(alias or "").strip().lower()
            if not clean_alias:
                return False
            alias_raw = f" {clean_alias} "
            alias_normalized = " " + re.sub(r"[^a-z0-9_]+", " ", clean_alias).strip() + " "
            return alias_raw in prompt_raw or alias_normalized in prompt_normalized

        if current_definition is not None:
            for node in current_definition.nodes:
                node_id = str(node.id or "").strip().lower()
                node_label = str(node.label or "").strip().lower()
                if node_id and _contains_alias(node_id):
                    _append_unique(node.type)
                if node_label and _contains_alias(node_label):
                    _append_unique(node.type)

        scored_matches: list[tuple[int, int, str]] = []
        for node_type in NODE_CONFIG_DEFAULTS:
            aliases: set[str] = set()
            raw = str(node_type).strip().lower()
            human = raw.replace("_", " ")
            aliases.add(raw)
            aliases.add(human)
            aliases.add(f"{human} node")
            if human.startswith("send "):
                aliases.add(human.replace("send ", "", 1))
            for extra in ASK_NODE_MANUAL_ALIASES.get(node_type, ()):
                aliases.add(str(extra).strip().lower())

            best_for_type = 0
            for alias in aliases:
                clean_alias = alias.strip()
                if len(clean_alias) < 3:
                    continue
                if _contains_alias(clean_alias):
                    score = len(clean_alias.split())
                    best_for_type = max(best_for_type, score)
            if best_for_type > 0:
                scored_matches.append((best_for_type, len(raw), node_type))

        if scored_matches:
            scored_matches.sort(reverse=True)
            for _score, _len_raw, node_type in scored_matches:
                _append_unique(node_type)

        return ordered_hits[: max(1, max_matches)]

    @classmethod
    def _classify_ask_intent(cls, prompt: str) -> str:
        lowered = f" {str(prompt or '').lower()} "

        has_routing = any(
            token in lowered
            for token in (
                "if_else",
                "if else",
                "switch",
                "routing",
                "branch",
                "branching",
                "priority path",
                "sentiment path",
                "category path",
            )
        )
        has_steps = any(
            token in lowered
            for token in ("steps", "step by step", "how to implement", "implementation", "where to place", "which place")
        )
        has_brief_request = any(
            token in lowered
            for token in (
                " workflow brief ",
                " give brief ",
                " brief of this workflow ",
                " brief this workflow ",
                " workflow summary ",
                " summary of this workflow ",
                " overview of this workflow ",
                " give overview ",
            )
        )
        has_upgrade = any(
            token in lowered
            for token in ("upgrade", "improve", "optimization", "optimize", "enhance", "better")
        )
        has_debug = any(
            token in lowered
            for token in (
                "fail",
                "not work",
                "not working",
                "error",
                "failed",
                "failing",
                "problem",
                "issue",
                "runtime",
                "exception",
                "waiting",
                "stuck",
                "not run",
                "not running",
                "not execute",
                "not executing",
                "timeout",
                "timed out",
                "status code",
                "not found",
                "bad gateway",
                "502",
                "404",
                "401",
                "403",
                "422",
                "429",
                "500",
                "503",
                "why false",
            )
        )
        has_capability = any(
            token in lowered
            for token in (
                "ask mode capability",
                "ask mode capabilities",
                "what can ask mode",
                "what ask mode can",
                "chatbot capability",
                "what this chatbot can do",
            )
        )
        has_mapping_validate = cls._looks_like_data_mapping_validation_prompt(prompt)
        has_schema_contract = cls._looks_like_schema_contract_prompt(prompt)
        has_merge_strategy = cls._looks_like_merge_strategy_prompt(prompt)
        has_loop_control = cls._looks_like_loop_control_prompt(prompt)
        has_trigger_config = cls._looks_like_trigger_configuration_prompt(prompt)
        has_credential_oauth = cls._looks_like_credential_oauth_prompt(prompt)
        has_execution_log_debug = cls._looks_like_execution_log_debug_prompt(prompt)
        has_reliability_patterns = cls._looks_like_reliability_patterns_prompt(prompt)
        has_performance_scaling = cls._looks_like_performance_scaling_prompt(prompt)
        has_security_pii = cls._looks_like_security_pii_prompt(prompt)
        has_publish_ops = cls._looks_like_publish_ops_prompt(prompt)
        has_n8n_migration = cls._looks_like_n8n_migration_prompt(prompt)
        has_parameter_help = any(
            token in lowered
            for token in ("parameter", "parameters", "config", "configuration", "what should i send", "payload")
        )

        if has_routing and (has_steps or has_parameter_help):
            return "routing"
        if has_capability:
            return "capability"
        if has_mapping_validate:
            return "mapping_validate"
        if has_schema_contract:
            return "schema_contract"
        if has_merge_strategy:
            return "merge_strategy"
        if has_loop_control:
            return "loop_control"
        if has_trigger_config:
            return "trigger_config"
        if has_credential_oauth:
            return "credential_oauth"
        if has_execution_log_debug:
            return "execution_log_debug"
        if has_reliability_patterns:
            return "reliability_patterns"
        if has_performance_scaling:
            return "performance_scaling"
        if has_security_pii:
            return "security_pii"
        if has_publish_ops:
            return "publish_ops"
        if has_n8n_migration:
            return "n8n_migration"
        if has_debug:
            return "debug"
        if has_steps:
            return "how_to"
        if has_parameter_help:
            return "parameter_help"
        if has_brief_request and has_upgrade:
            return "upgrade"
        if has_brief_request:
            return "brief"
        if has_upgrade:
            return "upgrade"
        if any(token in lowered for token in ("node", "what is", "what does", "explain")):
            return "node_explain"
        return "general"

    @classmethod
    def _build_multi_node_focus_response(
        cls,
        *,
        node_types: list[str],
        prompt: str,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        trimmed_types = node_types[:3]
        ordered_types = cls._order_node_types_for_multi_guidance(
            node_types=trimmed_types,
            current_definition=current_definition,
        )
        sections: list[str] = [
            "Direct answer:",
            f"- Your question touches {len(trimmed_types)} nodes, so here is the exact guidance for each in your current flow.",
            "I found multiple node targets in your question:",
            "- " + ", ".join(trimmed_types),
            "Combined placement guide:",
            "- Recommended chain: " + " -> ".join(f"`{node_type}`" for node_type in ordered_types),
            "- Wire each node output into the next node in the recommended chain.",
            "- Keep the same `input_key` across transform nodes when operating on one array.",
            "- After the final transform/logic node, connect to AI/delivery/storage nodes as needed.",
        ]
        for node_type in ordered_types:
            sections.append("")
            sections.append(
                cls._build_node_focus_response(
                    node_type=node_type,
                    prompt=prompt,
                    current_definition=current_definition,
                )
            )
        return "\n".join(sections)

    @classmethod
    def _order_node_types_for_multi_guidance(
        cls,
        *,
        node_types: list[str],
        current_definition: WorkflowDefinition | None,
    ) -> list[str]:
        ordered: list[str] = []
        allowed = [str(node_type).strip() for node_type in node_types if str(node_type).strip()]
        if not allowed:
            return []

        if current_definition is not None:
            allowed_set = set(allowed)
            for node in current_definition.nodes:
                if node.type in allowed_set and node.type not in ordered:
                    ordered.append(node.type)

        default_rank: dict[str, int] = {
            "webhook_trigger": 0,
            "form_trigger": 0,
            "schedule_trigger": 0,
            "manual_trigger": 0,
            "http_request": 1,
            "file_read": 1,
            "read_google_sheets": 1,
            "read_google_docs": 1,
            "code": 2,
            "filter": 3,
            "sort": 4,
            "limit": 5,
            "aggregate": 6,
            "ai_agent": 7,
            "if_else": 8,
            "switch": 8,
            "merge": 9,
            "search_update_google_sheets": 10,
            "create_google_docs": 10,
            "file_write": 10,
            "send_gmail_message": 11,
            "create_gmail_draft": 11,
            "add_gmail_label": 11,
            "telegram": 11,
            "whatsapp": 11,
            "slack_send_message": 11,
            "linkedin": 11,
        }

        missing = [node_type for node_type in allowed if node_type not in ordered]
        missing.sort(key=lambda node_type: (default_rank.get(node_type, 50), allowed.index(node_type)))
        for node_type in missing:
            if node_type not in ordered:
                ordered.append(node_type)
        return ordered[: len(allowed)]

    @classmethod
    def _build_required_parameter_hints(
        cls,
        *,
        node_type: str,
        details: Mapping[str, Any],
    ) -> list[str]:
        hints: list[str] = []
        description = str(details.get("description") or "").strip()
        if description:
            requires_match = re.search(r"requires?\s+([^.]+)", description, flags=re.IGNORECASE)
            if requires_match:
                fragment = " ".join(requires_match.group(1).split()).strip(" .")
                if fragment:
                    hints.append(fragment)

        for rule in details.get("rules") or []:
            rule_text = " ".join(str(rule or "").split()).strip()
            if not rule_text:
                continue
            lowered = rule_text.lower()
            if "required" in lowered:
                hints.append(rule_text)

        hard_required_map: dict[str, list[str]] = {
            "http_request": ["url", "method"],
            "send_gmail_message": ["credential_id", "to", "subject", "body"],
            "create_gmail_draft": ["credential_id", "to", "subject", "body"],
            "add_gmail_label": ["credential_id", "message_id", "label_name"],
            "telegram": ["credential_id", "message"],
            "whatsapp": ["credential_id", "to_number", "template_name"],
            "slack_send_message": ["credential_id", "message"],
            "linkedin": ["credential_id", "post_text"],
            "read_google_docs": ["credential_id", "document_source_type", "document_id OR document_url"],
            "read_google_sheets": ["credential_id", "spreadsheet_source_type", "spreadsheet_id OR spreadsheet_url", "sheet_name"],
            "if_else": ["condition_type", "conditions with field/operator/value OR value_field"],
            "switch": ["field", "cases", "default_case"],
            "merge": ["mode", "input_count"],
            "code": ["language", "code"],
            "file_read": ["file_path"],
            "file_write": ["file_path"],
            "ai_agent": ["command"],
        }
        for hint in hard_required_map.get(node_type, []):
            hints.append(hint)

        deduped: list[str] = []
        seen: set[str] = set()
        for hint in hints:
            normalized = " ".join(str(hint).split()).strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped[:5]

    @classmethod
    def _build_node_focus_response(
        cls,
        *,
        node_type: str,
        prompt: str,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        if node_type == "http_request":
            return cls._build_http_node_response(current_definition=current_definition)

        details = NODE_TYPE_DETAILS.get(node_type, {})
        defaults = NODE_CONFIG_DEFAULTS.get(node_type, {})
        description = str(details.get("description") or "").strip() or f"{node_type} node."
        rules = [
            str(rule).strip()
            for rule in (details.get("rules") or [])
            if str(rule).strip()
        ]

        lines = [
            "Direct answer:",
            f"- `{node_type}` {description}",
            f"Node: {node_type}",
        ]
        if isinstance(defaults, Mapping):
            config_keys = ", ".join(sorted(defaults.keys()))
            lines.append(f"Key parameters: {config_keys or 'No config keys'}")
            required_hints = cls._build_required_parameter_hints(
                node_type=node_type,
                details=details,
            )
            if required_hints:
                lines.append("Required parameters:")
                for index, hint in enumerate(required_hints, start=1):
                    lines.append(f"{index}. {hint}")
            if config_keys:
                example_keys = cls._select_parameter_example_keys(
                    node_type=node_type,
                    defaults=defaults,
                    prompt=prompt,
                )
                sample_items: list[str] = []
                for key in example_keys:
                    value = defaults.get(key)
                    sample_items.append(f"\"{key}\": {json.dumps(value, ensure_ascii=True)}")
                lines.append("Parameter examples:")
                lines.append(f"- {{{', '.join(sample_items)}}}")
                concrete_payload = {
                    key: defaults.get(key)
                    for key in example_keys
                }
                lines.append("Concrete parameter example from schema:")
                lines.append(f"- {cls._compact_json(concrete_payload, max_chars=340)}")
        if rules:
            lines.append("How to use:")
            for index, rule in enumerate(rules[:4], start=1):
                lines.append(f"{index}. {rule}")

        if current_definition is not None:
            nodes_by_id = {node.id: node for node in current_definition.nodes}
            matching_nodes = [node for node in current_definition.nodes if node.type == node_type]
            if matching_nodes:
                lines.append("In your current workflow:")
                for node in matching_nodes[:3]:
                    lines.append(f"- {node.label} ({node.id}) is present.")
                    config = node.config if isinstance(node.config, Mapping) else {}
                    non_empty_config = {
                        key: value
                        for key, value in config.items()
                        if value not in ("", None, [], {}, False)
                    }
                    if non_empty_config:
                        lines.append(f"  config preview: {cls._compact_json(non_empty_config)}")
                    incoming = [
                        edge for edge in current_definition.edges if edge.target == node.id
                    ][:2]
                    outgoing = [
                        edge for edge in current_definition.edges if edge.source == node.id
                    ][:2]
                    if incoming:
                        refs = []
                        for edge in incoming:
                            source = nodes_by_id.get(edge.source)
                            refs.append(f"{source.label if source else edge.source}->{node.id}")
                        lines.append(f"  incoming: {', '.join(refs)}")
                    if outgoing:
                        refs = []
                        for edge in outgoing:
                            target = nodes_by_id.get(edge.target)
                            refs.append(f"{node.id}->{target.label if target else edge.target}")
                        lines.append(f"  outgoing: {', '.join(refs)}")
                    anchor = cls._build_node_anchor_line(
                        node_id=node.id,
                        incoming_edges=incoming,
                        outgoing_edges=outgoing,
                        nodes_by_id=nodes_by_id,
                    )
                    if anchor:
                        lines.append(f"  placement anchor: {anchor}")
                first_node = matching_nodes[0]
                lines.append("Where to place/use it:")
                lines.append(
                    f"- Reuse `{first_node.label}` ({first_node.id}) at its current position in the flow."
                )
            else:
                lines.append("In your current workflow: this node is not present yet.")
                placement_hint = cls._resolve_node_placement_hint(
                    node_type=node_type,
                    definition=current_definition,
                )
                lines.append("Where to place/use it:")
                lines.append(f"- {placement_hint}")
        else:
            lines.append("Where to place/use it:")
            lines.append("- Add this after data preparation and before final outbound delivery nodes.")
        return "\n".join(lines)

    @classmethod
    def _select_parameter_example_keys(
        cls,
        *,
        node_type: str,
        defaults: Mapping[str, Any],
        prompt: str,
        max_keys: int = 4,
    ) -> list[str]:
        priority_map: dict[str, tuple[str, ...]] = {
            "if_else": ("condition_type", "conditions"),
            "switch": ("field", "cases", "default_case"),
            "webhook_trigger": ("path", "method"),
            "http_request": ("method", "url", "body_type", "body_json"),
            "merge": ("mode", "input_count"),
            "ai_agent": ("system_prompt", "command", "response_enhancement"),
            "chat_model_openai": ("model", "temperature", "max_tokens"),
            "chat_model_groq": ("model", "temperature", "max_tokens"),
            "search_update_google_sheets": (
                "operation",
                "sheet_name",
                "update_mappings",
                "key_column",
            ),
            "read_google_sheets": (
                "sheet_name",
                "spreadsheet_source_type",
                "first_row_as_header",
                "max_rows",
            ),
            "limit": ("input_key", "limit", "offset", "start_from"),
            "sort": ("input_key", "sort_by", "order", "data_type"),
            "read_google_docs": (
                "document_source_type",
                "document_id",
                "document_url",
                "max_characters",
            ),
            "send_gmail_message": ("to", "subject", "body", "is_html"),
            "create_gmail_draft": ("to", "subject", "body"),
            "add_gmail_label": ("message_id", "label_name", "credential_id"),
            "telegram": ("message", "parse_mode", "credential_id"),
            "whatsapp": ("to_number", "template_name", "template_params", "language_code"),
        }
        selected: list[str] = []
        for key in priority_map.get(node_type, ()):
            if key in defaults and key not in selected:
                selected.append(key)

        lowered_prompt = str(prompt or "").lower()
        for key in defaults:
            if key in selected:
                continue
            key_human = key.replace("_", " ")
            if key in lowered_prompt or key_human in lowered_prompt:
                selected.append(key)
                if len(selected) >= max_keys:
                    break

        for key in sorted(defaults.keys()):
            if key in selected:
                continue
            selected.append(key)
            if len(selected) >= max_keys:
                break
        return selected[:max_keys]

    @classmethod
    def _build_node_anchor_line(
        cls,
        *,
        node_id: str,
        incoming_edges: list[Any],
        outgoing_edges: list[Any],
        nodes_by_id: Mapping[str, Any],
    ) -> str:
        incoming_edge = incoming_edges[0] if incoming_edges else None
        outgoing_edge = outgoing_edges[0] if outgoing_edges else None
        source_id = incoming_edge.source if incoming_edge is not None else None
        target_id = outgoing_edge.target if outgoing_edge is not None else None
        source_label = (
            (nodes_by_id.get(source_id).label if nodes_by_id.get(source_id) else source_id)
            if source_id
            else None
        )
        target_label = (
            (nodes_by_id.get(target_id).label if nodes_by_id.get(target_id) else target_id)
            if target_id
            else None
        )

        if source_id and target_id:
            return (
                f"source=`{source_id}` ({source_label}) -> `{node_id}` -> "
                f"target=`{target_id}` ({target_label})"
            )
        if source_id:
            return f"source=`{source_id}` ({source_label}) -> `{node_id}`"
        if target_id:
            return f"`{node_id}` -> target=`{target_id}` ({target_label})"
        return ""

    @classmethod
    def _resolve_node_placement_hint(
        cls,
        *,
        node_type: str,
        definition: WorkflowDefinition,
    ) -> str:
        nodes_by_id = {node.id: node for node in definition.nodes}
        if node_type in {"if_else", "switch"}:
            return cls._resolve_routing_insertion_point(definition)
        if node_type in {"limit", "sort", "filter", "aggregate"}:
            return (
                f"Place `{node_type}` after the node that outputs your target array and before aggregation/delivery steps."
            )
        if node_type in {"telegram", "whatsapp", "send_gmail_message", "slack_send_message", "linkedin"}:
            for edge in definition.edges:
                source = nodes_by_id.get(edge.source)
                if source and source.type in {"ai_agent", "code", "merge", "if_else", "switch"}:
                    return (
                        f"Place `{node_type}` after `{source.label}` ({source.id}) on the branch where notification is required."
                    )
        if node_type in {"http_request", "file_write", "read_google_sheets", "search_update_google_sheets", "create_google_docs", "read_google_docs"}:
            for edge in definition.edges:
                source = nodes_by_id.get(edge.source)
                if source and source.type in {"code", "merge", "ai_agent"}:
                    return (
                        f"Place `{node_type}` after `{source.label}` ({source.id}) once payload fields are ready."
                    )
        trigger_nodes = [node for node in definition.nodes if node.type in TRIGGER_NODE_TYPES]
        if trigger_nodes:
            return (
                f"Place `{node_type}` after `{trigger_nodes[0].label}` ({trigger_nodes[0].id}) and before final delivery nodes."
            )
        return f"Place `{node_type}` after the step that prepares its required input fields."

    @classmethod
    def _build_http_node_response(
        cls,
        *,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lines = [
            "Direct answer:",
            "- HTTP node sends data from this workflow to an external API URL.",
            "HTTP Node Overview:",
            "- `http_request` sends an outbound API call from your workflow to an external endpoint.",
            "- It is not the incoming endpoint. Incoming requests should hit `webhook_trigger`.",
            "What you have to send:",
            "1. Set `method` (GET/POST/PUT/PATCH/DELETE).",
            "2. Set `url` to the target API endpoint where data must be sent.",
            "3. Choose `body_type` for methods like POST/PUT/PATCH:",
            "   - `json`: send payload in `body_json` (common case).",
            "   - `form`: send payload in `body_form_json`.",
            "   - `raw`: send payload in `body_raw`.",
            "4. If auth is needed, set `auth_mode` and corresponding auth fields.",
            "Where to send:",
            "- Send to the external service URL in `config.url` (for example your CRM/support API endpoint).",
            "- Use Autoflow templates in payload, for example `{\"ticket_id\":\"{{ticket_id}}\",\"summary\":\"{{output.summary}}\"}`.",
        ]

        if current_definition is not None:
            nodes_by_id = {node.id: node for node in current_definition.nodes}
            http_nodes = [node for node in current_definition.nodes if node.type == "http_request"]
            if http_nodes:
                lines.append("In your current workflow:")
                lines.append("HTTP nodes found in this workflow:")
                for node in http_nodes[:3]:
                    config = node.config if isinstance(node.config, Mapping) else {}
                    method = str(config.get("method") or "GET").upper()
                    url = str(config.get("url") or "").strip() or "[URL not set]"
                    auth_mode = str(config.get("auth_mode") or "none").strip()
                    body_type = str(config.get("body_type") or "none").strip()
                    lines.append(
                        f"- {node.label} ({node.id}): method={method}, url={url}, auth_mode={auth_mode}, body_type={body_type}"
                    )
                    incoming = [
                        edge for edge in current_definition.edges if edge.target == node.id
                    ][:2]
                    outgoing = [
                        edge for edge in current_definition.edges if edge.source == node.id
                    ][:2]
                    anchor = cls._build_node_anchor_line(
                        node_id=node.id,
                        incoming_edges=incoming,
                        outgoing_edges=outgoing,
                        nodes_by_id=nodes_by_id,
                    )
                    if anchor:
                        lines.append(f"  placement anchor: {anchor}")
            else:
                lines.append("In this workflow, no `http_request` node is present yet.")
                lines.append("Placement tip: add it after data preparation/classification and before final notification nodes.")

            webhook_nodes = [node for node in current_definition.nodes if node.type == "webhook_trigger"]
            if webhook_nodes:
                lines.append("Because your flow starts with webhook_trigger:")
                lines.append("- External client sends data to your webhook URL.")
                lines.append("- Then workflow can forward transformed data to external API via `http_request`.")
            lines.append("Where to place/use it:")
            lines.append(
                f"- {cls._resolve_node_placement_hint(node_type='http_request', definition=current_definition)}"
            )

        return "\n".join(lines)

    @classmethod
    def _build_routing_implementation_response(
        cls,
        *,
        definition: WorkflowDefinition | None,
        include_brief: bool,
    ) -> str:
        lines: list[str] = []
        if definition is not None and include_brief:
            lines.append("Workflow Brief:")
            for point in cls._render_workflow_brief_points(definition):
                lines.append(f"- {point}")

        placement_text = cls._resolve_routing_insertion_point(definition)
        recommended_field = cls._suggest_routing_field(definition)
        lines.append("Where to place it:")
        lines.append(f"- {placement_text}")

        lines.append("Implementation Steps:")
        lines.append("1. Add an `if_else` node right after AI output is available (before final delivery nodes).")
        lines.append(f"2. Configure condition on a routing field, recommended: `{recommended_field}`.")
        lines.append("3. Wire `true` branch to urgent/high-priority path and `false` branch to normal path.")
        lines.append("4. If you need 3+ categories, replace `if_else` with `switch` and create one case per route.")
        lines.append("5. Ensure every branch ends in required actions (save/log/notify), then optionally merge branches.")

        lines.append("if_else parameters (example):")
        lines.append(f'```json\n{{"condition_type":"AND","conditions":[{{"field":"{recommended_field}","operator":"equals","value":"negative","value_mode":"literal","value_field":"","case_sensitive":false}}]}}\n```')

        lines.append("switch parameters (example):")
        lines.append('```json\n{"field":"output.category","cases":[{"id":"billing_case","label":"Billing","operator":"equals","value":"billing"},{"id":"technical_case","label":"Technical","operator":"equals","value":"technical"}],"default_case":"general_case"}\n```')

        lines.append("Branch wiring:")
        lines.append("- `if_else`: outgoing edges must use `branch: \"true\"` and `branch: \"false\"`.")
        lines.append("- `switch`: outgoing edges must use `branch` equal to each case `id` (or `default_case`).")
        branch_map = cls._render_routing_branch_map(definition)
        if branch_map:
            lines.append("Branch map in your current workflow:")
            for item in branch_map:
                lines.append(f"- {item}")
        return "\n".join(lines)

    @classmethod
    def _suggest_routing_field(
        cls,
        definition: WorkflowDefinition | None,
    ) -> str:
        if definition is None:
            return "output.sentiment"

        for node in definition.nodes:
            if node.type in {"if_else", "switch"}:
                config = node.config if isinstance(node.config, Mapping) else {}
                field = str(config.get("field") or "").strip()
                if field:
                    return field

        for node in definition.nodes:
            config = node.config if isinstance(node.config, Mapping) else {}
            for candidate in ("priority", "category", "sentiment", "status"):
                value = str(config.get(candidate) or "").strip()
                if value:
                    return candidate

        if any(node.type == "ai_agent" for node in definition.nodes):
            return "output.sentiment"
        return "priority"

    @classmethod
    def _render_routing_branch_map(
        cls,
        definition: WorkflowDefinition | None,
    ) -> list[str]:
        if definition is None:
            return []
        nodes_by_id = {node.id: node for node in definition.nodes}
        lines: list[str] = []
        for node in definition.nodes:
            if node.type not in {"if_else", "switch"}:
                continue
            outgoing = [edge for edge in definition.edges if edge.source == node.id]
            if not outgoing:
                continue
            for edge in outgoing[:6]:
                target = nodes_by_id.get(edge.target)
                target_label = target.label if target is not None else edge.target
                branch_value = str(edge.branch or "default")
                lines.append(
                    f"`{node.id}` branch `{branch_value}` -> `{edge.target}` ({target_label})"
                )
            if lines:
                break
        return lines[:6]

    @classmethod
    def _resolve_routing_insertion_point(
        cls,
        definition: WorkflowDefinition | None,
    ) -> str:
        if definition is None:
            return "After the step that produces routing data (for example ai_agent), before your channel delivery nodes."

        nodes_by_id = {node.id: node for node in definition.nodes}
        ai_nodes = [node for node in definition.nodes if node.type == "ai_agent"]
        non_model_target_types = {
            node_id
            for node_id, node in nodes_by_id.items()
            if node.type not in AI_CHAT_MODEL_NODE_TYPES
        }

        for ai_node in ai_nodes:
            outgoing = [
                edge for edge in definition.edges
                if edge.source == ai_node.id and edge.target in non_model_target_types
            ]
            if outgoing:
                target_node = nodes_by_id.get(outgoing[0].target)
                target_label = target_node.label if target_node else outgoing[0].target
                return (
                    f"Insert routing between `{ai_node.label}` ({ai_node.id}) and `{target_label}` "
                    f"({outgoing[0].target})."
                )

        trigger_ids = {node.id for node in definition.nodes if node.type in TRIGGER_NODE_TYPES}
        for edge in definition.edges:
            if edge.source in trigger_ids and edge.target in nodes_by_id:
                target = nodes_by_id[edge.target]
                return (
                    f"Insert routing after trigger `{edge.source}` and before `{target.label}` "
                    f"({target.id}) once route fields are prepared."
                )

        return "Place routing right before outbound actions (Telegram/WhatsApp/Gmail/LinkedIn) after classification data is available."

    @classmethod
    def _render_workflow_brief_points(
        cls,
        definition: WorkflowDefinition,
    ) -> list[str]:
        node_count = len(definition.nodes)
        edge_count = len(definition.edges)
        trigger_node = next(
            (node for node in definition.nodes if node.type in TRIGGER_NODE_TYPES),
            None,
        )
        trigger_type = trigger_node.type if trigger_node is not None else "manual_trigger"
        main_steps = [
            cls._humanize_node_type(node.type)
            for node in definition.nodes
            if node.type not in TRIGGER_NODE_TYPES and node.type not in AI_CHAT_MODEL_NODE_TYPES
        ]
        rendered_steps = ", ".join(main_steps[:5]) if main_steps else "No downstream action nodes yet"
        branching_nodes = [node for node in definition.nodes if node.type in {"if_else", "switch"}]
        flow_shape = "branched" if branching_nodes else "linear"

        points = [
            f"This workflow has {node_count} nodes and {edge_count} edges.",
            f"Start trigger is `{trigger_type}`.",
            f"Main path: {rendered_steps}.",
            f"Flow shape: {flow_shape}.",
        ]
        if trigger_node is not None:
            points.append(f"Trigger node id: `{trigger_node.id}`.")
        if branching_nodes:
            points.append("Branch nodes: " + ", ".join(f"`{node.id}`" for node in branching_nodes[:3]) + ".")
        node_types = {node.type for node in definition.nodes}
        if "ai_agent" in node_types:
            points.append("It includes AI analysis using an ai_agent with structured output under `output.*`.")
        if {"telegram", "whatsapp", "send_gmail_message", "slack_send_message"} & node_types:
            points.append("It sends notifications through at least one messaging/email channel.")
        return points

    @classmethod
    def _suggest_workflow_upgrades(
        cls,
        definition: WorkflowDefinition | None,
    ) -> list[str]:
        if definition is None:
            return [
                "Choose trigger first from user intent (avoid manual trigger unless explicitly requested).",
                "Add early validation/cleanup before external integrations.",
                "Use condition nodes (if_else/switch) for routing instead of long linear chains.",
                "Use {{output.field}} for ai_agent structured output mappings.",
                "Add retries/error strategy on critical delivery nodes.",
            ]

        node_types = {node.type for node in definition.nodes}
        suggestions: list[str] = []
        trigger_type = next(
            (node.type for node in definition.nodes if node.type in TRIGGER_NODE_TYPES),
            None,
        )
        if trigger_type is None:
            suggestions.append(
                "Add exactly one trigger node so the workflow starts predictably."
            )
        if trigger_type == "webhook_trigger":
            suggestions.append(
                "Harden webhook entry with request auth verification and idempotency key handling to avoid duplicate tickets."
            )
        if "ai_agent" in node_types:
            suggestions.append(
                "Stabilize AI outputs by enforcing strict JSON keys and lowering temperature for consistent triage decisions."
            )
        if "if_else" not in node_types and "switch" not in node_types:
            suggestions.append(
                "Add explicit routing logic (if_else/switch) so priority, sentiment, or category paths are handled clearly."
            )
        if node_types & {"telegram", "whatsapp", "send_gmail_message", "slack_send_message", "linkedin", "http_request"}:
            suggestions.append(
                "Add delivery resilience: retry policy, fallback channel, and alert if any outbound integration fails."
            )
        if "merge" in node_types:
            suggestions.append(
                "Review merge mode and input counts so the save path never waits for an input branch that will not execute."
            )
        if cls._has_ai_agent_without_chat_model(definition):
            suggestions.append(
                "Connect each ai_agent to one chat_model node via targetHandle `chat_model` to avoid runtime AI execution failures."
            )
        if cls._has_http_request_without_url(definition):
            suggestions.append(
                "Set non-empty `url` for every http_request node and validate method/auth/payload contract before production runs."
            )
        if cls._has_template_syntax_risk(definition):
            suggestions.append(
                "Fix template syntax to use double braces `{{...}}` consistently (avoid single-brace placeholders)."
            )
        if cls._has_orphan_non_trigger_nodes(definition):
            suggestions.append(
                "Remove or connect orphan nodes that are not on an execution path so maintenance and debugging stay clear."
            )
        suggestions.append(
            "Add operational observability (execution logs + status fields) so failures are easy to trace per ticket/work item."
        )

        deduped: list[str] = []
        seen: set[str] = set()
        for item in suggestions:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:6]

    @classmethod
    def _has_ai_agent_without_chat_model(
        cls,
        definition: WorkflowDefinition,
    ) -> bool:
        nodes_by_id = {node.id: node for node in definition.nodes}
        ai_nodes = [node for node in definition.nodes if node.type == "ai_agent"]
        if not ai_nodes:
            return False
        for ai_node in ai_nodes:
            has_model = any(
                edge.target == ai_node.id
                and str(edge.targetHandle or "") == "chat_model"
                and nodes_by_id.get(edge.source) is not None
                and nodes_by_id[edge.source].type in AI_CHAT_MODEL_NODE_TYPES
                for edge in definition.edges
            )
            if not has_model:
                return True
        return False

    @classmethod
    def _has_http_request_without_url(
        cls,
        definition: WorkflowDefinition,
    ) -> bool:
        for node in definition.nodes:
            if node.type != "http_request":
                continue
            config = node.config if isinstance(node.config, Mapping) else {}
            if not str(config.get("url") or "").strip():
                return True
        return False

    @classmethod
    def _has_template_syntax_risk(
        cls,
        definition: WorkflowDefinition,
    ) -> bool:
        for node in definition.nodes:
            config = node.config if isinstance(node.config, Mapping) else {}
            for value in config.values():
                if not isinstance(value, str):
                    continue
                if TEMPLATE_SINGLE_BRACE_PATTERN.search(value):
                    return True
        return False

    @classmethod
    def _has_orphan_non_trigger_nodes(
        cls,
        definition: WorkflowDefinition,
    ) -> bool:
        incoming_count: dict[str, int] = {node.id: 0 for node in definition.nodes}
        outgoing_count: dict[str, int] = {node.id: 0 for node in definition.nodes}
        for edge in definition.edges:
            if edge.target in incoming_count:
                incoming_count[edge.target] += 1
            if edge.source in outgoing_count:
                outgoing_count[edge.source] += 1
        for node in definition.nodes:
            if node.type in TRIGGER_NODE_TYPES or node.type in AI_CHAT_MODEL_NODE_TYPES:
                continue
            if incoming_count.get(node.id, 0) == 0 and outgoing_count.get(node.id, 0) == 0:
                return True
        return False

    @staticmethod
    def _modify_prompt_allows_full_rebuild(prompt: str) -> bool:
        lowered = prompt.lower()
        rebuild_tokens = (
            "rebuild",
            "recreate",
            "replace entire",
            "replace whole",
            "from scratch",
            "start over",
            "completely new",
            "full redesign",
        )
        return any(token in lowered for token in rebuild_tokens)

    @staticmethod
    def _is_broad_modify_change(
        *,
        previous_definition: WorkflowDefinition,
        updated_definition: WorkflowDefinition,
    ) -> bool:
        old_nodes = {node.id: node for node in previous_definition.nodes}
        new_nodes = {node.id: node for node in updated_definition.nodes}
        if not old_nodes:
            return False

        removed_nodes = set(old_nodes) - set(new_nodes)
        added_nodes = set(new_nodes) - set(old_nodes)
        shared_ids = set(old_nodes) & set(new_nodes)

        changed_shared_nodes = {
            node_id
            for node_id in shared_ids
            if old_nodes[node_id].type != new_nodes[node_id].type
            or old_nodes[node_id].config != new_nodes[node_id].config
        }

        old_edge_signatures = {
            (edge.source, edge.target, str(edge.branch or ""), str(edge.targetHandle or ""))
            for edge in previous_definition.edges
        }
        new_edge_signatures = {
            (edge.source, edge.target, str(edge.branch or ""), str(edge.targetHandle or ""))
            for edge in updated_definition.edges
        }
        edge_delta_count = len(old_edge_signatures ^ new_edge_signatures)
        edge_delta_threshold = max(6, int(max(1, len(old_edge_signatures)) * 0.8) + 2)

        removed_ratio = len(removed_nodes) / max(1, len(old_nodes))
        changed_ratio = len(changed_shared_nodes) / max(1, len(old_nodes))

        return (
            removed_ratio > 0.35
            or (changed_ratio > 0.75 and len(added_nodes) > 0)
            or edge_delta_count >= edge_delta_threshold
        )

    @staticmethod
    def _sanitize_string_list(raw_values: Any) -> list[str]:
        if not isinstance(raw_values, list):
            return []
        return [
            " ".join(str(value).split()).strip()
            for value in raw_values
            if " ".join(str(value).split()).strip()
        ]

    @staticmethod
    def _sanitize_single_line(raw_value: Any, *, max_chars: int = 260) -> str:
        normalized = " ".join(str(raw_value or "").split()).strip()
        if not normalized:
            return ""
        return normalized[:max_chars]

    @classmethod
    def _sanitize_node_reference_list(cls, raw_values: Any) -> list[str]:
        if not isinstance(raw_values, list):
            return []
        sanitized: list[str] = []
        seen: set[str] = set()
        for item in raw_values[:12]:
            normalized = cls._sanitize_single_line(item, max_chars=120).lower()
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            sanitized.append(normalized)
        return sanitized[:6]

    @staticmethod
    def _sanitize_recent_messages(raw_values: Any) -> list[dict[str, str]]:
        if not isinstance(raw_values, list):
            return []
        sanitized: list[dict[str, str]] = []
        for item in raw_values[-8:]:
            if not isinstance(item, Mapping):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = " ".join(str(item.get("content") or "").split()).strip()
            if not content:
                continue
            sanitized.append({"role": role, "content": content[:220]})
        return sanitized

    @staticmethod
    def _append_recent_chat_context_to_prompt(
        prompt: str,
        *,
        recent_messages: list[dict[str, str]],
    ) -> str:
        if not recent_messages:
            return prompt
        lines = [f"- {item['role']}: {item['content']}" for item in recent_messages if item.get("content")]
        if not lines:
            return prompt
        return f"{prompt}\n\nRecent chat context:\n" + "\n".join(lines)

    @staticmethod
    def _append_memory_anchors_to_prompt(
        prompt: str,
        *,
        last_referenced_nodes: list[str],
        last_unresolved_question: str,
        last_accepted_workflow_signature: str,
    ) -> str:
        lines: list[str] = []
        if last_referenced_nodes:
            lines.append(
                f"- Last referenced nodes: {', '.join(last_referenced_nodes[:5])}"
            )
        if last_unresolved_question:
            lines.append(f"- Last unresolved question: {last_unresolved_question}")
        if last_accepted_workflow_signature:
            lines.append(
                f"- Last accepted workflow signature: {last_accepted_workflow_signature[:120]}"
            )
        if not lines:
            return prompt
        return f"{prompt}\n\nConversation memory anchors:\n" + "\n".join(lines)

    @staticmethod
    def _dedupe_non_empty_strings(values: list[Any]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = " ".join(str(value).split()).strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped

    @classmethod
    def _strip_sensitive_config_values(cls, definition: WorkflowDefinition) -> WorkflowDefinition:
        payload = definition.model_dump()
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            return definition

        for node in nodes:
            if not isinstance(node, dict):
                continue
            config = node.get("config")
            if not isinstance(config, dict):
                continue
            for key in ASSISTANT_SENSITIVE_CONFIG_KEYS:
                if key in config:
                    config[key] = ""

        try:
            return WorkflowDefinition.model_validate(payload)
        except ValidationError:
            return definition

    @staticmethod
    def _summarize_definition_changes(
        *,
        previous_definition: WorkflowDefinition,
        updated_definition: WorkflowDefinition,
    ) -> str:
        old_nodes = {node.id: node for node in previous_definition.nodes}
        new_nodes = {node.id: node for node in updated_definition.nodes}

        added_node_ids = sorted(set(new_nodes) - set(old_nodes))
        removed_node_ids = sorted(set(old_nodes) - set(new_nodes))
        changed_type_ids = sorted(
            node_id
            for node_id in (set(old_nodes) & set(new_nodes))
            if old_nodes[node_id].type != new_nodes[node_id].type
        )
        changed_config_ids = sorted(
            node_id
            for node_id in (set(old_nodes) & set(new_nodes))
            if old_nodes[node_id].type == new_nodes[node_id].type
            and old_nodes[node_id].config != new_nodes[node_id].config
        )

        old_edge_signatures = {
            (
                edge.source,
                edge.target,
                str(edge.branch or ""),
                str(edge.targetHandle or ""),
            )
            for edge in previous_definition.edges
        }
        new_edge_signatures = {
            (
                edge.source,
                edge.target,
                str(edge.branch or ""),
                str(edge.targetHandle or ""),
            )
            for edge in updated_definition.edges
        }
        added_edges = max(0, len(new_edge_signatures - old_edge_signatures))
        removed_edges = max(0, len(old_edge_signatures - new_edge_signatures))

        summary_parts: list[str] = []
        if added_node_ids:
            summary_parts.append(f"added nodes: {', '.join(added_node_ids[:5])}")
        if removed_node_ids:
            summary_parts.append(f"removed nodes: {', '.join(removed_node_ids[:5])}")
        if changed_type_ids:
            summary_parts.append(f"retargeted node types: {', '.join(changed_type_ids[:5])}")
        if changed_config_ids:
            summary_parts.append(f"updated configs: {', '.join(changed_config_ids[:5])}")
        if added_edges or removed_edges:
            summary_parts.append(f"edge changes: +{added_edges}/-{removed_edges}")

        if not summary_parts:
            return "No major structural changes detected; response mostly refined existing configuration."
        return " | ".join(summary_parts)

    @classmethod
    def build_workflow_generation_system_prompt(cls) -> str:
        node_sections: list[str] = []
        for node_type, default_config in NODE_CONFIG_DEFAULTS.items():
            details = NODE_TYPE_DETAILS.get(node_type, {})
            description = details.get("description", "Use exactly this node type and config shape.")
            rules = details.get("rules", [])
            rendered_rules = "\n".join(f"  - {rule}" for rule in rules)
            node_sections.append(
                "\n".join(
                    part
                    for part in (
                        f"- {node_type}",
                        f"  category: {details.get('category', 'unknown')}",
                        f"  description: {description}",
                        f"  config schema/defaults: {json.dumps(default_config, sort_keys=True)}",
                        rendered_rules if rendered_rules else "",
                    )
                    if part
                )
            )

        return dedent(
            f"""
            You generate Autoflow workflow definitions from user requests.

            Return ONLY one valid JSON object.
            Do not return markdown.
            Do not wrap the JSON in code fences.
            Do not add explanation, notes, comments, or prose.
            The top-level object must be either:
            1. a workflow definition object with keys "nodes" and "edges", or
            2. an object with "definition", optional "name", and optional "message" keys where definition is the workflow, name is the workflow title, and message is null unless the sub-workflow rule below applies.

            Required workflow shape:
            {{
              "nodes": [
                {{
                  "id": "string",
                  "type": "string",
                  "label": "string",
                  "position": {{"x": 0, "y": 0}},
                  "config": {{}}
                }}
              ],
              "edges": [
                {{
                  "id": "string",
                  "source": "node_id",
                  "target": "node_id",
                  "sourceHandle": null,
                  "targetHandle": null,
                  "branch": null
                }}
              ]
            }}

            Workflow rules:
            - Use only these node types, exactly as written.
            - Every node id must be unique.
            - Every edge id must be unique.
            - Every edge source and target must reference existing node ids.
            - The graph must be a DAG. Do not create cycles.
            - Include exactly one start trigger node with indegree 0.
            - Valid trigger node types are: {", ".join(sorted(TRIGGER_NODE_TYPES))}.
            - Every workflow should be minimal but complete for the user request.
            - Never return a trigger-only workflow when the user requested downstream actions, logic, integrations, or outputs.
            - Use clear human-readable labels.
            - position.x and position.y must be numbers.
            - Always include a config object, even when it is empty.
            - For dummy integration nodes, keep unresolved user-specific values as empty strings instead of inventing secrets, ids, or credentials.
            - Never invent extra config keys that are not part of the schema below.
            - If you use ai_agent, also include exactly one connected chat_model_openai or chat_model_groq node for it.
            - Chat model nodes are configuration sub-nodes, not normal workflow steps.
            - If the user asks to generate or include an AI-created image/visual, use an image_gen node. Do not replace image generation with ai_agent text.
            - When an Image Gen result must be posted, emailed, or sent onward, connect image_gen before the destination node and set the destination image field to {{{{image_gen_node_id.image_base64}}}} or {{{{image_gen_node_id.image_url}}}}.
            - Think step-by-step internally: infer trigger, identify major actions, then connect nodes in execution order.
            - Prefer explicit integration nodes when the user names a channel (Telegram, Gmail, Slack, WhatsApp, Sheets, Docs, LinkedIn).
            - Use real templating placeholders for dynamic values (for example {{email}}, {{form.email}}, {{items}}, {{response.body.id}}).
            - Never use single-brace placeholders like {{email}} or {{form.email}}; always use double braces {{{{email}}}} or {{{{form.email}}}}.
            - For complex requests, include all required intermediate logic nodes (if_else, switch, filter, merge, split_in/split_out, aggregate, delay) instead of collapsing logic into one node.
            - If the request asks for an N-day sequence, design a clear day-by-day cadence and keep timing consistent with the requested duration.
            - If the request asks to use multiple channels (for example email + WhatsApp + Telegram), fan out into parallel channel branches from the trigger (or immediately after one router node) instead of serially chaining all channels in one line.
            - Sub-workflow detection is mandatory. If the user's prompt implies calling one workflow from another, triggering a sub-process, or reusing a workflow inside another workflow (for example "call a sub-workflow", "trigger another workflow", "reuse workflow X inside Y", "run a child workflow", or "execute a workflow within a workflow"), generate ONLY the parent workflow JSON.
            - PARENT WORKFLOW TRIGGER SELECTION RULES — follow strictly:
              - User mentions "webhook", "API", "receives data", "HTTP", or "POST" -> use webhook_trigger.
              - User mentions "form", "user fills", "user submits", or "user input" -> use form_trigger.
              - User mentions "schedule", "every day", "every hour", "cron", "daily", or "weekly" -> use schedule_trigger.
              - User mentions "another workflow", "sub-workflow", or "child workflow" -> use manual_trigger ONLY for the parent if no other trigger is mentioned.
              - NEVER default to manual_trigger just because it is the simplest option.
              - Read the user's prompt carefully and pick the trigger that matches the use case.
            - For sub-workflow parent workflows, include an execute_workflow node with config.source="database" and config.workflow_id="" because the child workflow does not exist yet.
            - For sub-workflow parent workflows, append the message field exactly as: "{SUB_WORKFLOW_RESPONSE_MESSAGE}"
            - Never generate both parent and child in a single definition. One generation equals one workflow.
            - A child workflow must always start with a workflow_trigger node.
            - The parent workflow uses execute_workflow to call the child. Since this builder generates one workflow at a time, when the user asks for a sub-workflow pattern, generate the parent workflow and use the message field to explain that a separate child workflow is needed.
            - Never place workflow_trigger anywhere except as the first node of a workflow.
            - Never place more than one workflow_trigger per workflow.

            Edge rules:
            - Standard linear edges may omit branch or set it to null.
            - Edges leaving if_else must set branch to "true" or "false".
            - Edges leaving switch must set branch to a case id or the default_case value.
            - sourceHandle and targetHandle should usually be null unless a frontend handle name is explicitly needed.
            - Edges leaving chat_model_openai or chat_model_groq must target an ai_agent and set targetHandle to "chat_model".

            Node type list and config schemas:
            {chr(10).join(node_sections)}
            """
        ).strip()

    @staticmethod
    def _build_generation_user_prompt(
        prompt: str,
        *,
        validation_error: str | None = None,
    ) -> str:
        validation_suffix = ""
        if validation_error:
            validation_suffix = (
                "\n\nValidation issues from your previous response:\n"
                f"- {validation_error}\n"
                "Fix every issue and regenerate the full workflow JSON."
            )
        return dedent(
            f"""
            User request:
            {prompt}

            Generation checklist:
            1. Pick the best trigger from the request intent (avoid manual_trigger unless the user explicitly asks for manual/on-demand runs).
            2. Include all necessary nodes to complete the business flow end-to-end.
            3. Fill node configs using the schema keys and realistic defaults/placeholders.
            4. Wire edges correctly, including branch labels for if_else/switch.
            5. If ai_agent exists, connect exactly one chat model sub-node to targetHandle "chat_model".
            6. Always use Autoflow template syntax {{...}} for dynamic values; do not use single braces.
            7. If the request specifies a multi-day sequence (for example 14-day), ensure cadence/timing truly matches that duration.
            8. For multi-channel nurture flows, branch channels in parallel rather than chaining all channels serially.
            9. If the request asks for generated images or AI-created visuals, include an image_gen node with model, prompt, size, quality, and style config.
            10. Keep workflow complexity proportional: use the minimum nodes needed for simple requests, and add logic nodes only when they are clearly required.
            11. For ai_agent structured outputs, reference downstream fields using {{output.field_name}} (for example {{output.summary}}).
            12. Do not return trigger-only output for actionable prompts; include the needed downstream steps.
            13. Return only one JSON object; no explanation text.
            14. If this is a sub-workflow parent pattern, return an object with definition and message. The definition must be only the parent workflow, with execute_workflow.source="database" and execute_workflow.workflow_id="".
            {validation_suffix}
            """
        ).strip()

    @classmethod
    def validate_generated_workflow(
        cls,
        raw_content: str,
        *,
        user_prompt: str | None = None,
        include_response_message: bool = False,
    ) -> tuple[WorkflowDefinition, str | None] | tuple[WorkflowDefinition, str | None, str | None]:
        if not raw_content.strip():
            raise WorkflowGenerationError("Model response was empty.")

        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise WorkflowGenerationError(f"Model returned invalid JSON: {exc.msg}") from exc

        if not isinstance(payload, Mapping):
            raise WorkflowGenerationError("Workflow definition must be a JSON object.")

        definition_payload = payload.get("definition", payload)
        if not isinstance(definition_payload, Mapping):
            raise WorkflowGenerationError("Workflow definition must be a JSON object.")

        hinted_payload = cls._apply_prompt_hints_to_definition_payload(
            definition_payload,
            user_prompt=user_prompt,
        )
        sanitized_definition_payload = cls._sanitize_generated_definition_payload(hinted_payload)

        try:
            definition = WorkflowDefinition.model_validate(sanitized_definition_payload)
        except ValidationError as exc:
            raise WorkflowGenerationError(str(exc)) from exc

        cls._validate_node_types(definition)
        cls._validate_trigger_structure(definition)
        cls._validate_branch_edges(definition)
        cls._validate_ai_subnode_structure(definition)
        cls._validate_delay_configs(definition)
        cls._validate_placeholder_syntax(definition)
        cls._validate_minimum_workflow_usefulness(definition, user_prompt=user_prompt)
        cls._validate_sequence_duration_expectation(definition, user_prompt=user_prompt)
        cls._validate_multi_channel_branching_expectation(definition, user_prompt=user_prompt)
        cls._validate_complexity_alignment(definition, user_prompt=user_prompt)
        cls._validate_image_generation_expectation(definition, user_prompt=user_prompt)
        cls._validate_sub_workflow_expectation(definition, user_prompt=user_prompt)
        workflow_name = cls._extract_workflow_name(payload)
        response_message = cls._extract_workflow_message(payload)
        if include_response_message:
            return definition, workflow_name, response_message
        return definition, workflow_name

    @classmethod
    def _sanitize_generated_definition_payload(
        cls,
        definition_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        sanitized: dict[str, Any] = deepcopy(dict(definition_payload))
        raw_nodes = sanitized.get("nodes")
        if isinstance(raw_nodes, list):
            sanitized_nodes: list[Any] = []
            for raw_node in raw_nodes:
                if not isinstance(raw_node, Mapping):
                    sanitized_nodes.append(raw_node)
                    continue

                node = deepcopy(dict(raw_node))
                node_type = str(node.get("type") or "").strip()
                defaults = NODE_CONFIG_DEFAULTS.get(node_type)
                raw_config = node.get("config")
                if defaults is not None:
                    filtered_config: dict[str, Any] = {}
                    if isinstance(raw_config, Mapping):
                        filtered_config = {
                            key: value
                            for key, value in raw_config.items()
                            if key in defaults
                        }
                    node["config"] = {
                        **deepcopy(defaults),
                        **filtered_config,
                    }
                    node["config"] = cls._normalize_config_values(
                        node_type=node_type,
                        config=node["config"],
                    )

                label = str(node.get("label") or "").strip()
                if not label and node_type:
                    node["label"] = cls._humanize_node_type(node_type)

                sanitized_nodes.append(node)
            sanitized["nodes"] = sanitized_nodes

        raw_edges = sanitized.get("edges")
        if isinstance(raw_edges, list):
            sanitized_edges: list[Any] = []
            for raw_edge in raw_edges:
                if not isinstance(raw_edge, Mapping):
                    sanitized_edges.append(raw_edge)
                    continue
                edge = deepcopy(dict(raw_edge))
                for nullable_key in ("sourceHandle", "targetHandle", "branch"):
                    if nullable_key in edge and str(edge.get(nullable_key) or "").strip() == "":
                        edge[nullable_key] = None
                sanitized_edges.append(edge)
            sanitized["edges"] = sanitized_edges

        sanitized = cls._normalize_ai_agent_placeholder_paths(sanitized)

        return sanitized

    @classmethod
    def _normalize_config_values(
        cls,
        *,
        node_type: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = cls._normalize_template_placeholders(config)

        return normalized

    @classmethod
    def _normalize_template_placeholders(cls, value: Any) -> Any:
        if isinstance(value, str):
            return TEMPLATE_SINGLE_BRACE_PATTERN.sub(r"{{\1}}", value)
        if isinstance(value, list):
            return [cls._normalize_template_placeholders(item) for item in value]
        if isinstance(value, dict):
            return {
                key: cls._normalize_template_placeholders(item)
                for key, item in value.items()
            }
        return value

    @classmethod
    def _normalize_ai_agent_placeholder_paths(
        cls,
        definition_payload: dict[str, Any],
    ) -> dict[str, Any]:
        raw_nodes = definition_payload.get("nodes")
        if not isinstance(raw_nodes, list):
            return definition_payload

        ai_agent_node_ids = {
            str(node.get("id") or "").strip()
            for node in raw_nodes
            if isinstance(node, Mapping)
            and str(node.get("type") or "").strip() == "ai_agent"
            and str(node.get("id") or "").strip()
        }
        if not ai_agent_node_ids:
            return definition_payload

        normalized_nodes: list[Any] = []
        for raw_node in raw_nodes:
            if not isinstance(raw_node, Mapping):
                normalized_nodes.append(raw_node)
                continue

            node = deepcopy(dict(raw_node))
            config = node.get("config")
            if isinstance(config, dict):
                node["config"] = cls._normalize_ai_agent_placeholder_in_value(
                    config,
                    ai_agent_node_ids=ai_agent_node_ids,
                )
            normalized_nodes.append(node)

        return {
            **definition_payload,
            "nodes": normalized_nodes,
        }

    @classmethod
    def _normalize_ai_agent_placeholder_in_value(
        cls,
        value: Any,
        *,
        ai_agent_node_ids: set[str],
    ) -> Any:
        if isinstance(value, str):
            def _replacer(match: re.Match[str]) -> str:
                expression = str(match.group(1) or "").strip()
                normalized_expression = cls._normalize_ai_agent_expression(
                    expression,
                    ai_agent_node_ids=ai_agent_node_ids,
                )
                if normalized_expression == expression:
                    return match.group(0)
                return f"{{{{{normalized_expression}}}}}"

            return TEMPLATE_DOUBLE_BRACE_PATTERN.sub(_replacer, value)
        if isinstance(value, list):
            return [
                cls._normalize_ai_agent_placeholder_in_value(
                    item,
                    ai_agent_node_ids=ai_agent_node_ids,
                )
                for item in value
            ]
        if isinstance(value, dict):
            return {
                key: cls._normalize_ai_agent_placeholder_in_value(
                    item,
                    ai_agent_node_ids=ai_agent_node_ids,
                )
                for key, item in value.items()
            }
        return value

    @classmethod
    def _normalize_ai_agent_expression(
        cls,
        expression: str,
        *,
        ai_agent_node_ids: set[str],
    ) -> str:
        normalized = expression.strip()
        for node_id in sorted(ai_agent_node_ids):
            direct_prefix = f"{node_id}."
            if normalized.startswith(direct_prefix):
                suffix = normalized[len(direct_prefix):]
                if suffix.startswith("output."):
                    return suffix
                if cls._should_route_to_ai_output(suffix):
                    return f"output.{suffix}"

            for quote in ('"', "'"):
                node_prefix = f"$node[{quote}{node_id}{quote}].json."
                if normalized.startswith(node_prefix):
                    suffix = normalized[len(node_prefix):]
                    if suffix.startswith("output."):
                        return suffix
                    if cls._should_route_to_ai_output(suffix):
                        return f"output.{suffix}"
        return normalized

    @staticmethod
    def _should_route_to_ai_output(suffix: str) -> bool:
        normalized_suffix = str(suffix or "").strip()
        if not normalized_suffix:
            return False
        if normalized_suffix.startswith(
            (
                "output.",
                "ai_metadata.",
                "chat_model.",
                "memory.",
                "tool.",
            )
        ):
            return False
        first_segment = normalized_suffix.split(".", 1)[0].strip()
        return first_segment in AI_AGENT_STRUCTURED_OUTPUT_KEYS

    @classmethod
    def _apply_prompt_hints_to_definition_payload(
        cls,
        definition_payload: Mapping[str, Any],
        *,
        user_prompt: str | None,
    ) -> dict[str, Any]:
        hinted: dict[str, Any] = deepcopy(dict(definition_payload))
        if not user_prompt:
            return hinted

        prompt_text = user_prompt.strip()
        if not prompt_text:
            return hinted

        raw_nodes = hinted.get("nodes")
        raw_edges = hinted.get("edges")
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            return hinted

        preferred_trigger_type = (
            cls._infer_parent_trigger_type_from_prompt(prompt_text)
            if cls._prompt_implies_sub_workflow(prompt_text)
            else cls._infer_trigger_type_from_prompt(prompt_text)
        )
        start_trigger_index = cls._find_start_trigger_node_index(raw_nodes, raw_edges)
        if (
            not preferred_trigger_type
            and start_trigger_index is not None
            and isinstance(raw_nodes[start_trigger_index], Mapping)
        ):
            start_type = str(raw_nodes[start_trigger_index].get("type") or "").strip()
            if start_type == "manual_trigger":
                preferred_trigger_type = cls._infer_default_trigger_from_prompt(
                    prompt=prompt_text,
                    inferred_trigger=None,
                )
        if (
            preferred_trigger_type
            and start_trigger_index is not None
            and isinstance(raw_nodes[start_trigger_index], Mapping)
        ):
            start_node = deepcopy(dict(raw_nodes[start_trigger_index]))
            current_type = str(start_node.get("type") or "").strip()
            if current_type != preferred_trigger_type:
                defaults = deepcopy(NODE_CONFIG_DEFAULTS.get(preferred_trigger_type, {}))
                existing_config = start_node.get("config")
                if isinstance(existing_config, Mapping):
                    for key, value in existing_config.items():
                        if key in defaults:
                            defaults[key] = value
                if preferred_trigger_type == "schedule_trigger":
                    defaults = cls._hydrate_schedule_config_from_prompt(defaults, prompt_text)
                elif preferred_trigger_type == "form_trigger":
                    defaults = cls._hydrate_form_config_from_prompt(defaults, prompt_text)
                elif preferred_trigger_type == "webhook_trigger":
                    defaults = cls._hydrate_webhook_config_from_prompt(defaults, prompt_text)
                start_node["type"] = preferred_trigger_type
                start_node["config"] = defaults
                if not str(start_node.get("label") or "").strip():
                    start_node["label"] = cls._humanize_node_type(preferred_trigger_type)
                raw_nodes[start_trigger_index] = start_node
            elif preferred_trigger_type == "schedule_trigger":
                schedule_config = cls._hydrate_schedule_config_from_prompt(
                    start_node.get("config"),
                    prompt_text,
                )
                start_node["config"] = schedule_config
                raw_nodes[start_trigger_index] = start_node
            elif preferred_trigger_type == "form_trigger":
                form_config = cls._hydrate_form_config_from_prompt(
                    start_node.get("config"),
                    prompt_text,
                )
                start_node["config"] = form_config
                raw_nodes[start_trigger_index] = start_node
            elif preferred_trigger_type == "webhook_trigger":
                webhook_config = cls._hydrate_webhook_config_from_prompt(
                    start_node.get("config"),
                    prompt_text,
                )
                start_node["config"] = webhook_config
                raw_nodes[start_trigger_index] = start_node

        preferred_chat_model_type = cls._infer_chat_model_type_from_prompt(prompt_text)
        if preferred_chat_model_type:
            for index, raw_node in enumerate(raw_nodes):
                if not isinstance(raw_node, Mapping):
                    continue
                node_type = str(raw_node.get("type") or "").strip()
                if node_type not in AI_CHAT_MODEL_NODE_TYPES or node_type == preferred_chat_model_type:
                    continue
                node = deepcopy(dict(raw_node))
                node["type"] = preferred_chat_model_type
                node["label"] = cls._humanize_node_type(preferred_chat_model_type)
                node["config"] = cls._convert_chat_model_config(
                    raw_config=node.get("config"),
                    target_node_type=preferred_chat_model_type,
                )
                raw_nodes[index] = node

        hinted["nodes"] = raw_nodes
        hinted["edges"] = raw_edges
        return hinted

    @staticmethod
    def _infer_trigger_type_from_prompt(prompt: str) -> str | None:
        lowered = f" {prompt.lower()} "

        # Highest-confidence direct intent first.
        for trigger_type in ("workflow_trigger", "schedule_trigger", "form_trigger", "webhook_trigger"):
            keywords = next(
                (tokens for candidate, tokens in TRIGGER_KEYWORD_HINTS if candidate == trigger_type),
                (),
            )
            if any(keyword in lowered for keyword in keywords):
                return trigger_type

        if LLMService._extract_schedule_rule_from_prompt(prompt) is not None:
            return "schedule_trigger"

        manual_keywords = next(
            (tokens for candidate, tokens in TRIGGER_KEYWORD_HINTS if candidate == "manual_trigger"),
            (),
        )
        explicit_manual = any(keyword in lowered for keyword in manual_keywords)
        has_event_language = any(token in lowered for token in EVENT_LANGUAGE_HINTS)
        has_form_intent = any(token in lowered for token in FORM_INTENT_HINTS)
        has_webhook_source = any(token in lowered for token in WEBHOOK_SOURCE_HINTS)

        # If user explicitly requested manual execution, preserve that choice.
        if explicit_manual:
            return "manual_trigger"

        if has_event_language and has_form_intent:
            return "form_trigger"
        if has_event_language and has_webhook_source:
            return "webhook_trigger"
        return None

    @staticmethod
    def _infer_chat_model_type_from_prompt(prompt: str) -> str | None:
        lowered = prompt.lower()
        mentions_openai = any(token in lowered for token in ("openai", "gpt-4", "gpt-5", "chatgpt"))
        mentions_groq = any(token in lowered for token in ("groq", "llama-3", "mixtral"))
        if mentions_openai and mentions_groq:
            return None
        if mentions_groq:
            return "chat_model_groq"
        if mentions_openai:
            return "chat_model_openai"
        return None

    @staticmethod
    def _prompt_requests_image_generation(prompt: str) -> bool:
        lowered = prompt.lower()
        return any(keyword in lowered for keyword in IMAGE_GENERATION_HINTS)

    @staticmethod
    def _find_start_trigger_node_index(nodes: list[Any], edges: list[Any]) -> int | None:
        node_ids = {
            str(node.get("id") or "").strip()
            for node in nodes
            if isinstance(node, Mapping) and str(node.get("id") or "").strip()
        }
        if not node_ids:
            return None

        indegree = {node_id: 0 for node_id in node_ids}
        for edge in edges:
            if not isinstance(edge, Mapping):
                continue
            target = str(edge.get("target") or "").strip()
            if target in indegree:
                indegree[target] += 1

        for index, node in enumerate(nodes):
            if not isinstance(node, Mapping):
                continue
            node_id = str(node.get("id") or "").strip()
            node_type = str(node.get("type") or "").strip()
            if node_type in TRIGGER_NODE_TYPES and indegree.get(node_id, 0) == 0:
                return index
        return None

    @classmethod
    def _hydrate_schedule_config_from_prompt(
        cls,
        existing_config: Any,
        prompt: str,
    ) -> dict[str, Any]:
        defaults = deepcopy(NODE_CONFIG_DEFAULTS["schedule_trigger"])
        config: dict[str, Any] = {}
        if isinstance(existing_config, Mapping):
            config = {
                key: value
                for key, value in existing_config.items()
                if key in defaults
            }

        timezone = str(config.get("timezone") or "").strip()
        resolved_timezone = timezone or defaults["timezone"]
        enabled = config.get("enabled")
        if enabled is None:
            enabled = True

        rule = cls._extract_schedule_rule_from_prompt(prompt)
        rules = [rule] if rule else deepcopy(defaults.get("rules", []))

        return {
            **defaults,
            **config,
            "timezone": resolved_timezone,
            "enabled": bool(enabled),
            "rules": rules,
        }

    @classmethod
    def _hydrate_form_config_from_prompt(
        cls,
        existing_config: Any,
        prompt: str,
    ) -> dict[str, Any]:
        defaults = deepcopy(NODE_CONFIG_DEFAULTS["form_trigger"])
        config: dict[str, Any] = {}
        if isinstance(existing_config, Mapping):
            config = {
                key: value
                for key, value in existing_config.items()
                if key in defaults
            }

        lowered = prompt.lower()
        field_catalog: list[dict[str, Any]] = [
            {"name": "name", "label": "Full Name", "type": "text"},
            {"name": "email", "label": "Email", "type": "email"},
            {"name": "age", "label": "Age", "type": "number"},
            {"name": "phone", "label": "Phone", "type": "phone", "default_country_code": "+91"},
            {"name": "website", "label": "Website", "type": "url"},
            {"name": "company", "label": "Company", "type": "text"},
            {"name": "message", "label": "Message", "type": "textarea"},
            {"name": "title", "label": "Title", "type": "text"},
            {"name": "date_of_birth", "label": "Date of Birth", "type": "date"},
            {"name": "appointment_date", "label": "Appointment Date", "type": "date"},
            {"name": "meeting_time", "label": "Meeting Time", "type": "time"},
            {"name": "scheduled_at", "label": "Scheduled At", "type": "datetime"},
            {"name": "subscribed", "label": "Subscribed", "type": "checkbox"},
            {"name": "satisfaction", "label": "Satisfaction", "type": "rating", "max_stars": 5},
            {
                "name": "contact_method",
                "label": "Contact Method",
                "type": "radio",
                "layout": "stacked",
                "options": [
                    {"label": "Email", "value": "email"},
                    {"label": "Phone", "value": "phone"},
                ],
            },
            {
                "name": "affected_platforms",
                "label": "Affected Platforms",
                "type": "checkbox_group",
                "options": [
                    {"label": "Gmail", "value": "gmail"},
                    {"label": "Google Sheets", "value": "sheets"},
                    {"label": "Telegram", "value": "telegram"},
                ],
            },
        ]
        keyword_aliases: dict[str, tuple[str, ...]] = {
            "name": ("name", "full name"),
            "email": ("email", "e-mail"),
            "age": ("age",),
            "phone": ("phone", "mobile", "contact number", "whatsapp number"),
            "website": ("website", "url", "site"),
            "company": ("company", "organization"),
            "message": ("message", "feedback", "comment", "query", "question"),
            "title": ("title", "subject"),
            "date_of_birth": ("date of birth", "dob", "birth date", "birthday"),
            "appointment_date": ("appointment date", "booking date", "visit date"),
            "meeting_time": ("meeting time", "appointment time", "current time", "time"),
            "scheduled_at": ("scheduled at", "date and time", "datetime", "schedule time"),
            "subscribed": ("subscribe", "subscribed", "newsletter", "opt in", "opt-in"),
            "satisfaction": ("rating", "satisfaction", "stars", "score"),
            "contact_method": ("contact method", "preferred contact", "reach by"),
            "affected_platforms": ("affected platforms", "platforms", "apps", "applications", "services affected"),
        }

        inferred_fields: list[dict[str, Any]] = []
        for field_config in field_catalog:
            field_name = str(field_config.get("name") or "").strip()
            aliases = keyword_aliases.get(field_name, (field_name,))
            if any(alias in lowered for alias in aliases):
                inferred_fields.append(
                    {
                        **deepcopy(field_config),
                        "required": field_name in {"name", "email"},
                    }
                )

        existing_fields = config.get("fields")
        normalized_existing_fields: list[dict[str, Any]] = []
        if isinstance(existing_fields, list):
            for item in existing_fields:
                if isinstance(item, Mapping):
                    normalized_existing_fields.append(dict(item))

        merged_fields_by_name: dict[str, dict[str, Any]] = {}
        for item in normalized_existing_fields + inferred_fields:
            field_name = str(item.get("name") or "").strip()
            if not field_name:
                continue
            merged_fields_by_name[field_name] = item

        merged_fields = list(merged_fields_by_name.values())
        if not merged_fields:
            merged_fields = deepcopy(defaults.get("fields", []))

        form_title = str(config.get("form_title") or "").strip()
        if not form_title:
            if "feedback" in lowered:
                form_title = "Feedback Form"
            elif "lead" in lowered:
                form_title = "Lead Capture Form"
            elif "signup" in lowered or "register" in lowered:
                form_title = "Signup Form"
            else:
                form_title = str(defaults.get("form_title") or "Form Submission")

        form_description = str(config.get("form_description") or "").strip()
        if not form_description:
            if "feedback" in lowered:
                form_description = "Collect customer feedback."
            elif "lead" in lowered:
                form_description = "Collect lead information for follow-up."
            elif "signup" in lowered or "register" in lowered:
                form_description = "Capture new signup details."
            else:
                form_description = str(defaults.get("form_description") or "")

        return {
            **defaults,
            **config,
            "form_title": form_title,
            "form_description": form_description,
            "fields": merged_fields,
        }

    @classmethod
    def _hydrate_webhook_config_from_prompt(
        cls,
        existing_config: Any,
        prompt: str,
    ) -> dict[str, Any]:
        defaults = deepcopy(NODE_CONFIG_DEFAULTS["webhook_trigger"])
        config: dict[str, Any] = {}
        if isinstance(existing_config, Mapping):
            config = {
                key: value
                for key, value in existing_config.items()
                if key in defaults
            }

        lowered = prompt.lower()
        path = str(config.get("path") or "").strip()
        method = str(config.get("method") or "").strip().upper()

        extracted_path = re.search(r"/[a-z0-9/_-]{2,}", lowered)
        if not path:
            if extracted_path:
                path = extracted_path.group(0).lstrip("/")
            elif "lead" in lowered:
                path = "leads/new"
            elif "order" in lowered:
                path = "orders/new"
            elif "ticket" in lowered:
                path = "tickets/new"
            else:
                path = "events/incoming"

        if not method:
            method = cls._extract_webhook_method_from_prompt(prompt) or "POST"

        return {
            **defaults,
            **config,
            "path": path,
            "method": method,
        }

    @staticmethod
    def _extract_webhook_method_from_prompt(prompt: str) -> str | None:
        lowered = prompt.lower()
        for method in ("POST", "PUT", "PATCH", "DELETE", "GET", "OPTIONS", "HEAD"):
            if f" {method.lower()} " in f" {lowered} ":
                return method
        return None

    @staticmethod
    def _extract_schedule_rule_from_prompt(prompt: str) -> dict[str, Any] | None:
        lowered = prompt.lower()
        cron_match = re.search(
            r"cron(?:\s+expression)?\s*[:=]\s*([^\n;,]+)",
            lowered,
        )
        if cron_match:
            cron_value = cron_match.group(1).strip()
            if cron_value:
                return {
                    "id": "rule_1",
                    "interval": "custom",
                    "cron": cron_value,
                    "enabled": True,
                }

        match = re.search(
            r"\bevery\s+(\d+)?\s*(minute|minutes|min|hour|hours|day|days|week|weeks|month|months)\b",
            lowered,
        )
        if not match:
            return None

        raw_every = match.group(1)
        every = int(raw_every) if raw_every else 1
        unit = match.group(2)
        interval = {
            "minute": "minutes",
            "minutes": "minutes",
            "min": "minutes",
            "hour": "hours",
            "hours": "hours",
            "day": "days",
            "days": "days",
            "week": "weeks",
            "weeks": "weeks",
            "month": "months",
            "months": "months",
        }[unit]

        rule: dict[str, Any] = {
            "id": "rule_1",
            "interval": interval,
            "every": every,
            "trigger_minute": 0,
            "trigger_hour": 0,
            "trigger_weekday": 1,
            "trigger_day_of_month": 1,
            "enabled": True,
        }
        return rule

    @staticmethod
    def _convert_chat_model_config(
        *,
        raw_config: Any,
        target_node_type: str,
    ) -> dict[str, Any]:
        defaults = deepcopy(NODE_CONFIG_DEFAULTS[target_node_type])
        if not isinstance(raw_config, Mapping):
            return defaults

        for key in ("credential_id", "temperature", "max_tokens"):
            if key in raw_config:
                defaults[key] = raw_config[key]

        raw_model = str(raw_config.get("model") or "").strip()
        if raw_model:
            looks_openai_model = raw_model.startswith("gpt-") or "openai" in raw_model.lower()
            looks_groq_model = (
                "llama" in raw_model.lower()
                or "mixtral" in raw_model.lower()
                or "qwen" in raw_model.lower()
            )
            if target_node_type == "chat_model_openai":
                defaults["model"] = (
                    defaults["model"] if looks_groq_model else raw_model
                )
            else:
                defaults["model"] = (
                    defaults["model"] if looks_openai_model else raw_model
                )

        return defaults

    @staticmethod
    def _humanize_node_type(node_type: str) -> str:
        return " ".join(part.capitalize() for part in node_type.split("_"))

    @staticmethod
    def _extract_workflow_name(payload: Mapping[str, Any]) -> str | None:
        for key in ("name", "workflow_name", "title"):
            value = payload.get(key)
            if isinstance(value, str):
                normalized = " ".join(value.split())
                if normalized:
                    return normalized[:100]
        return None

    @staticmethod
    def _extract_workflow_message(payload: Mapping[str, Any]) -> str | None:
        value = payload.get("message")
        if not isinstance(value, str):
            return None
        normalized = " ".join(value.split())
        return normalized[:1000] if normalized else None

    @staticmethod
    def _prompt_implies_sub_workflow(prompt: str) -> bool:
        lowered = re.sub(r"[\s_]+", " ", str(prompt or "").lower())
        return any(hint in lowered for hint in SUB_WORKFLOW_INTENT_HINTS)

    @classmethod
    def _build_sub_workflow_parent_fallback(cls, prompt: str) -> GeneratedWorkflowResult:
        trigger_type = cls._infer_parent_trigger_type_from_prompt(prompt)
        trigger_config = deepcopy(NODE_CONFIG_DEFAULTS.get(trigger_type, {}))
        if trigger_type == "webhook_trigger":
            trigger_config = cls._hydrate_webhook_config_from_prompt(
                trigger_config,
                prompt,
            )
            if not str(trigger_config.get("path") or "").strip():
                trigger_config["path"] = "parent-sub-workflow"
            trigger_config["method"] = str(trigger_config.get("method") or "POST").upper()
        elif trigger_type == "form_trigger":
            trigger_config = cls._hydrate_form_config_from_prompt(trigger_config, prompt)
        elif trigger_type == "schedule_trigger":
            trigger_config = cls._hydrate_schedule_config_from_prompt(trigger_config, prompt)

        trigger_id = trigger_type
        execute_id = "execute_child_workflow"
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": trigger_id,
                        "type": trigger_type,
                        "label": cls._humanize_node_type(trigger_type),
                        "position": {"x": 100, "y": 160},
                        "config": trigger_config,
                    },
                    {
                        "id": execute_id,
                        "type": "execute_workflow",
                        "label": "Execute Child Workflow",
                        "position": {"x": 380, "y": 160},
                        "config": {
                            "source": "database",
                            "workflow_id": "",
                            "workflow_json": "",
                            "workflow_inputs": [],
                            "mode": "run_once",
                        },
                    },
                ],
                "edges": [
                    {
                        "id": f"{trigger_id}_to_{execute_id}",
                        "source": trigger_id,
                        "target": execute_id,
                        "sourceHandle": None,
                        "targetHandle": None,
                        "branch": None,
                    }
                ],
            }
        )
        return GeneratedWorkflowResult(
            definition=definition,
            name=cls._derive_workflow_name(prompt),
            message=SUB_WORKFLOW_RESPONSE_MESSAGE,
        )

    @classmethod
    def _infer_parent_trigger_type_from_prompt(cls, prompt: str) -> str:
        lowered = f" {str(prompt or '').lower()} "
        if any(
            token in lowered
            for token in (
                "webhook",
                " api ",
                "receives data",
                "receive data",
                "http",
                " post ",
                "incoming payload",
                "incoming event",
            )
        ):
            return "webhook_trigger"
        if any(
            token in lowered
            for token in (
                " form",
                "user fills",
                "user submits",
                "user input",
                "submission",
            )
        ):
            return "form_trigger"
        if any(
            token in lowered
            for token in (
                "schedule",
                "every day",
                "every hour",
                "cron",
                "daily",
                "weekly",
                "hourly",
            )
        ) or cls._extract_schedule_rule_from_prompt(prompt) is not None:
            return "schedule_trigger"

        inferred_trigger = cls._infer_trigger_type_from_prompt(prompt)
        if inferred_trigger in {"webhook_trigger", "form_trigger", "schedule_trigger"}:
            return inferred_trigger
        default_trigger = cls._infer_default_trigger_from_prompt(
            prompt=prompt,
            inferred_trigger=None,
        )
        if default_trigger in {"webhook_trigger", "form_trigger", "schedule_trigger"}:
            return default_trigger
        return "manual_trigger"

    @staticmethod
    def _derive_workflow_name(prompt: str) -> str:
        base_prompt = prompt.split("\n\nCurrent canvas summary:", 1)[0]
        text = re.sub(r"\s+", " ", base_prompt.strip())
        if not text:
            return "AI Generated Workflow"

        lower = text.lower()
        prefixes = (
            "create a workflow that",
            "create workflow that",
            "build a workflow that",
            "build workflow that",
            "generate a workflow that",
            "generate workflow that",
            "create a workflow to",
            "create workflow to",
            "build a workflow to",
            "build workflow to",
            "generate a workflow to",
            "generate workflow to",
        )
        for prefix in prefixes:
            if lower.startswith(prefix):
                text = text[len(prefix) :].strip()
                break

        text = text.strip(" .,:;-")
        if not text:
            return "AI Generated Workflow"

        words = text.split()
        compact = " ".join(words[:9]) if len(words) > 9 else text
        return compact[:100]

    def _get_client(self) -> Any:
        if self.client is not None:
            return self.client

        if not self._api_key:
            raise WorkflowGenerationError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )

        self.client = get_provider("openai", self._api_key)
        return self.client

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise WorkflowGenerationError("Model response did not include any choices.")

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [
                item.text
                for item in content
                if getattr(item, "type", None) == "text" and getattr(item, "text", None)
            ]
            if text_parts:
                return "".join(text_parts)
        raise WorkflowGenerationError("Model response did not include text content.")

    def _resolve_generation_temperature(self) -> float | None:
        configured_temperature = os.getenv("OPENAI_WORKFLOW_TEMPERATURE")
        if configured_temperature is None:
            return self._default_temperature_for_model(self.model)

        normalized_temperature = configured_temperature.strip()
        if not normalized_temperature:
            return None

        try:
            return float(normalized_temperature)
        except ValueError as exc:
            raise WorkflowGenerationError(
                "OPENAI_WORKFLOW_TEMPERATURE must be numeric or empty."
            ) from exc

    @staticmethod
    def _default_temperature_for_model(model: str) -> float | None:
        normalized_model = model.strip().lower()
        if normalized_model.startswith("gpt-5"):
            return None
        return 0.0

    @staticmethod
    def _validate_node_types(definition: WorkflowDefinition) -> None:
        allowed_node_types = set(NODE_CONFIG_DEFAULTS)
        unknown_types = sorted(
            {
                node.type
                for node in definition.nodes
                if node.type not in allowed_node_types
            }
        )
        if unknown_types:
            raise WorkflowGenerationError(
                "Workflow contains unsupported node types: "
                + ", ".join(unknown_types)
            )

    @staticmethod
    def _validate_trigger_structure(definition: WorkflowDefinition) -> None:
        node_ids = {node.id for node in definition.nodes}
        indegree = {node.id: 0 for node in definition.nodes}

        for edge in definition.edges:
            if edge.source not in node_ids:
                raise WorkflowGenerationError(
                    f"Edge '{edge.id}' has non-existent source node '{edge.source}'."
                )
            if edge.target not in node_ids:
                raise WorkflowGenerationError(
                    f"Edge '{edge.id}' targets non-existent node '{edge.target}'."
                )
            indegree[edge.target] += 1

        start_triggers = [
            node.id
            for node in definition.nodes
            if node.type in TRIGGER_NODE_TYPES and indegree[node.id] == 0
        ]
        if len(start_triggers) != 1:
            raise WorkflowGenerationError(
                "Workflow must contain exactly one trigger node with indegree 0."
            )

        workflow_triggers = [
            (index, node)
            for index, node in enumerate(definition.nodes)
            if node.type == "workflow_trigger"
        ]
        if len(workflow_triggers) > 1:
            raise WorkflowGenerationError("Workflow can contain only one workflow_trigger node.")
        if workflow_triggers:
            index, trigger = workflow_triggers[0]
            if index != 0:
                raise WorkflowGenerationError("workflow_trigger must be the first node in the workflow.")
            if indegree.get(trigger.id, 0) != 0:
                raise WorkflowGenerationError("workflow_trigger must not have incoming edges.")

    @staticmethod
    def _validate_branch_edges(definition: WorkflowDefinition) -> None:
        nodes_by_id = {node.id: node for node in definition.nodes}
        outgoing_edges: dict[str, list[Any]] = {node.id: [] for node in definition.nodes}
        for edge in definition.edges:
            outgoing_edges.setdefault(edge.source, []).append(edge)

        for node_id, node in nodes_by_id.items():
            node_edges = outgoing_edges[node_id]
            if node.type == "if_else":
                invalid_edges = [
                    edge.id
                    for edge in node_edges
                    if str(edge.branch or edge.sourceHandle or "").strip() not in {"true", "false"}
                ]
                if invalid_edges:
                    raise WorkflowGenerationError(
                        "if_else edges must use branch 'true' or 'false'. "
                        f"Invalid edge ids: {', '.join(invalid_edges)}"
                    )

            if node.type == "switch":
                allowed_branches = {
                    str(case.get("id") or "").strip()
                    for case in node.config.get("cases", [])
                    if isinstance(case, dict) and str(case.get("id") or "").strip()
                }
                default_case = str(node.config.get("default_case") or "").strip()
                if default_case:
                    allowed_branches.add(default_case)

                invalid_edges = [
                    edge.id
                    for edge in node_edges
                    if str(edge.branch or edge.sourceHandle or "").strip() not in allowed_branches
                ]
                if invalid_edges:
                    raise WorkflowGenerationError(
                        "switch edges must use a valid case id or default_case. "
                        f"Invalid edge ids: {', '.join(invalid_edges)}"
                    )

    @staticmethod
    def _validate_ai_subnode_structure(definition: WorkflowDefinition) -> None:
        nodes_by_id = {node.id: node for node in definition.nodes}
        incoming_edges: dict[str, list[Any]] = {node.id: [] for node in definition.nodes}
        outgoing_edges: dict[str, list[Any]] = {node.id: [] for node in definition.nodes}

        for edge in definition.edges:
            incoming_edges.setdefault(edge.target, []).append(edge)
            outgoing_edges.setdefault(edge.source, []).append(edge)

        for node in definition.nodes:
            if node.type not in AI_CHAT_MODEL_NODE_TYPES:
                continue

            invalid_edges = [
                edge.id
                for edge in outgoing_edges[node.id]
                if nodes_by_id[edge.target].type != "ai_agent"
                or edge.targetHandle != "chat_model"
            ]
            if invalid_edges:
                raise WorkflowGenerationError(
                    "Chat model nodes must connect only to ai_agent nodes using "
                    "targetHandle 'chat_model'. "
                    f"Invalid edge ids: {', '.join(invalid_edges)}"
                )

        for node in definition.nodes:
            if node.type != "ai_agent":
                continue

            chat_model_edges = [
                edge
                for edge in incoming_edges[node.id]
                if nodes_by_id[edge.source].type in AI_CHAT_MODEL_NODE_TYPES
            ]
            if len(chat_model_edges) != 1:
                raise WorkflowGenerationError(
                    f"ai_agent node '{node.id}' must have exactly one connected "
                    "chat_model_openai or chat_model_groq sub-node."
                )

            edge = chat_model_edges[0]
            if edge.targetHandle != "chat_model":
                raise WorkflowGenerationError(
                    f"ai_agent node '{node.id}' must receive its chat model on "
                    "targetHandle 'chat_model'."
                )

    @staticmethod
    def _validate_delay_configs(definition: WorkflowDefinition) -> None:
        allowed_modes = {
            "",
            "after_interval",
            "until_datetime",
        }
        allowed_units = {
            "seconds",
            "minutes",
            "hours",
            "days",
            "months",
            "second",
            "minute",
            "hour",
            "day",
            "month",
        }
        for node in definition.nodes:
            if node.type != "delay":
                continue
            wait_mode = str(node.config.get("wait_mode") or "").strip().lower()
            if wait_mode not in allowed_modes:
                raise WorkflowGenerationError(
                    f"Delay node '{node.id}' has unsupported wait_mode '{wait_mode}'. "
                    "Use after_interval or until_datetime."
                )
            normalized_mode = wait_mode or (
                "until_datetime"
                if str(node.config.get("until_datetime") or "").strip()
                else "after_interval"
            )
            unit = str(node.config.get("unit") or "").strip().lower()
            if normalized_mode == "after_interval" and unit and unit not in allowed_units:
                raise WorkflowGenerationError(
                    f"Delay node '{node.id}' has unsupported unit '{unit}'. "
                    "Use seconds, minutes, hours, days, or months."
                )
            if normalized_mode == "after_interval" and not str(node.config.get("amount") or "").strip():
                raise WorkflowGenerationError(
                    f"Delay node '{node.id}' requires amount for wait_mode='after_interval'."
                )
            if normalized_mode == "until_datetime" and not str(node.config.get("until_datetime") or "").strip():
                raise WorkflowGenerationError(
                    f"Delay node '{node.id}' requires until_datetime for wait_mode='until_datetime'."
                )

    @classmethod
    def _validate_placeholder_syntax(cls, definition: WorkflowDefinition) -> None:
        single_brace_hits: list[str] = []
        for node in definition.nodes:
            config_values = cls._iter_scalar_strings(node.config)
            for value in config_values:
                if TEMPLATE_SINGLE_BRACE_PATTERN.search(value):
                    single_brace_hits.append(node.id)
                    break
        if single_brace_hits:
            raise WorkflowGenerationError(
                "Workflow contains invalid single-brace template placeholders. "
                "Use {{...}} syntax. "
                f"Affected node ids: {', '.join(single_brace_hits)}"
            )

    @classmethod
    def _validate_minimum_workflow_usefulness(
        cls,
        definition: WorkflowDefinition,
        *,
        user_prompt: str | None,
    ) -> None:
        if not user_prompt or not cls._prompt_requires_non_trigger_steps(user_prompt):
            return

        non_trigger_nodes = [
            node for node in definition.nodes if node.type not in TRIGGER_NODE_TYPES
        ]
        if not non_trigger_nodes:
            raise WorkflowGenerationError(
                "Generated workflow is trigger-only for an actionable prompt. "
                "Add the required downstream action/logic nodes."
            )

        start_trigger_id = cls._resolve_start_trigger_node_id(definition)
        if not start_trigger_id:
            return
        has_outgoing_from_trigger = any(
            edge.source == start_trigger_id for edge in definition.edges
        )
        if not has_outgoing_from_trigger:
            raise WorkflowGenerationError(
                "Generated workflow does not connect the trigger to downstream steps. "
                "Add edges from the start trigger to action/logic nodes."
            )

    @classmethod
    def _validate_sequence_duration_expectation(
        cls,
        definition: WorkflowDefinition,
        *,
        user_prompt: str | None,
    ) -> None:
        if not user_prompt:
            return
        normalized_prompt = user_prompt.lower()
        if "sequence" not in normalized_prompt:
            return

        match = SEQUENCE_DAYS_PATTERN.search(normalized_prompt)
        if not match:
            return
        requested_days = int(match.group(1) or match.group(2) or 0)
        if requested_days < 2:
            return

        total_hours = 0.0
        for node in definition.nodes:
            if node.type != "delay":
                continue
            unit = str(node.config.get("unit") or "").strip().lower()
            amount_raw = node.config.get("amount")
            if amount_raw is None:
                continue
            try:
                amount = float(str(amount_raw).strip())
            except Exception:
                continue

            unit_hours = {
                "hour": 1.0,
                "hours": 1.0,
                "minute": 1.0 / 60.0,
                "minutes": 1.0 / 60.0,
                "second": 1.0 / 3600.0,
                "seconds": 1.0 / 3600.0,
                "day": 24.0,
                "days": 24.0,
                "month": 24.0 * 30.0,
                "months": 24.0 * 30.0,
            }.get(unit)
            if unit_hours is None:
                continue
            total_hours += amount * unit_hours

        minimum_hours = max(0.0, float(requested_days - 1) * 24.0 * 0.8)
        if total_hours and total_hours < minimum_hours:
            raise WorkflowGenerationError(
                "Sequence duration does not match the requested timeline. "
                f"Requested about {requested_days} days but generated delays total only "
                f"{total_hours:.1f} hours."
            )

    @classmethod
    def _validate_multi_channel_branching_expectation(
        cls,
        definition: WorkflowDefinition,
        *,
        user_prompt: str | None,
    ) -> None:
        if not user_prompt:
            return

        prompt = user_prompt.lower()
        branching_intent_tokens = (
            "parallel",
            "in parallel",
            "fan out",
            "fanout",
            "branch into",
            "branch out",
            "split across channels",
        )
        if not any(token in prompt for token in branching_intent_tokens):
            return

        requested_channels = cls._infer_requested_channel_node_types(prompt)
        if len(requested_channels) < 2:
            return

        start_trigger_id = cls._resolve_start_trigger_node_id(definition)
        if not start_trigger_id:
            return

        outgoing_targets = {
            edge.target
            for edge in definition.edges
            if edge.source == start_trigger_id
        }
        if len(outgoing_targets) < len(requested_channels):
            raise WorkflowGenerationError(
                "Prompt requests multi-channel branching, but workflow does not fan out enough "
                f"branches from start trigger '{start_trigger_id}'. Expected at least "
                f"{len(requested_channels)} branches."
            )

    @classmethod
    def _validate_complexity_alignment(
        cls,
        definition: WorkflowDefinition,
        *,
        user_prompt: str | None,
    ) -> None:
        if not user_prompt:
            return

        analysis = cls._analyze_prompt_for_assistant(user_prompt)
        signals = analysis.get("signals") if isinstance(analysis, Mapping) else {}
        if not isinstance(signals, Mapping):
            return

        complexity_level = str(signals.get("complexity_level") or "").strip()
        if complexity_level != "simple":
            return

        non_sub_nodes = [
            node
            for node in definition.nodes
            if node.type not in AI_CHAT_MODEL_NODE_TYPES
        ]
        if len(non_sub_nodes) <= 6:
            return

        logic_heavy_types = {
            "if_else",
            "switch",
            "filter",
            "merge",
            "split_in",
            "split_out",
            "aggregate",
            "delay",
        }
        logic_node_count = sum(
            1
            for node in non_sub_nodes
            if node.type in logic_heavy_types
        )
        has_split_loop = any(node.type in {"split_in", "split_out"} for node in non_sub_nodes)
        requested_channels = {
            str(item).strip()
            for item in (signals.get("requested_channels") or [])
            if str(item).strip()
        }
        if len(requested_channels) >= 2:
            return

        if has_split_loop or (len(non_sub_nodes) >= 8 and logic_node_count >= 3):
            raise WorkflowGenerationError(
                "Generated workflow appears unnecessarily complex for a straightforward request. "
                "Prefer a concise structure with only essential steps."
            )

    @staticmethod
    def _infer_requested_channel_node_types(prompt: str) -> set[str]:
        requested: set[str] = set()
        for node_type, tokens in ASSISTANT_CHANNEL_HINTS.items():
            if any(token in prompt for token in tokens):
                requested.add(node_type)
        return requested

    @classmethod
    def _prompt_requires_non_trigger_steps(cls, prompt: str) -> bool:
        lowered = prompt.lower()
        if "only manual trigger" in lowered or "only a manual trigger" in lowered:
            return False
        if "trigger only" in lowered or "only trigger" in lowered:
            return False

        if cls._prompt_requests_image_generation(lowered):
            return True
        if cls._infer_requested_channel_node_types(lowered):
            return True
        if any(token in lowered for token in ASSISTANT_COMPLETION_HINTS):
            return True
        if any(token in lowered for token in ASSISTANT_BRANCH_HINTS):
            return True
        if any(token in lowered for token in ASSISTANT_TIMING_HINTS):
            return True
        return False

    @classmethod
    def _validate_image_generation_expectation(
        cls,
        definition: WorkflowDefinition,
        *,
        user_prompt: str | None,
    ) -> None:
        if not user_prompt or not cls._prompt_requests_image_generation(user_prompt):
            return

        image_gen_nodes = [node for node in definition.nodes if node.type == "image_gen"]
        if not image_gen_nodes:
            raise WorkflowGenerationError(
                "Prompt asks for generated images/visuals, but the workflow does not include an image_gen node."
            )

        empty_prompt_node_ids = [
            node.id
            for node in image_gen_nodes
            if not str(node.config.get("prompt") or "").strip()
        ]
        if empty_prompt_node_ids:
            raise WorkflowGenerationError(
                "Image Gen nodes must include a non-empty prompt config. "
                f"Affected node ids: {', '.join(empty_prompt_node_ids)}"
            )

    @classmethod
    def _validate_sub_workflow_expectation(
        cls,
        definition: WorkflowDefinition,
        *,
        user_prompt: str | None,
    ) -> None:
        if not user_prompt or not cls._prompt_implies_sub_workflow(user_prompt):
            return

        execute_nodes = [node for node in definition.nodes if node.type == "execute_workflow"]
        if not execute_nodes:
            raise WorkflowGenerationError(
                "Prompt asks for a sub-workflow pattern, but the parent workflow does not include an execute_workflow node."
            )
        workflow_triggers = [node for node in definition.nodes if node.type == "workflow_trigger"]
        if workflow_triggers:
            raise WorkflowGenerationError(
                "Sub-workflow pattern generation must return only the parent workflow; do not include workflow_trigger in the parent."
            )
        invalid_execute_nodes = [
            node.id
            for node in execute_nodes
            if str(node.config.get("source") or "database").strip().lower() != "database"
            or str(node.config.get("workflow_id") or "").strip()
        ]
        if invalid_execute_nodes:
            raise WorkflowGenerationError(
                "Sub-workflow parent execute_workflow nodes must use source=database and workflow_id=\"\". "
                f"Affected node ids: {', '.join(invalid_execute_nodes)}"
            )

    @staticmethod
    def _resolve_start_trigger_node_id(definition: WorkflowDefinition) -> str | None:
        node_ids = {node.id for node in definition.nodes}
        indegree = {node.id: 0 for node in definition.nodes}
        for edge in definition.edges:
            if edge.source in node_ids and edge.target in node_ids:
                indegree[edge.target] += 1

        for node in definition.nodes:
            if node.type in TRIGGER_NODE_TYPES and indegree.get(node.id, 0) == 0:
                return node.id
        return None

    @classmethod
    def _iter_scalar_strings(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            values: list[str] = []
            for item in value:
                values.extend(cls._iter_scalar_strings(item))
            return values
        if isinstance(value, dict):
            values = []
            for item in value.values():
                values.extend(cls._iter_scalar_strings(item))
            return values
        return []
