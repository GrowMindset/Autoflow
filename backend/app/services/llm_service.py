from __future__ import annotations

import json
import os
import re
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
    "slack_send_message": ("slack",),
    "telegram": ("telegram", "telegarm", "telegrm"),
    "whatsapp": ("whatsapp", "watsapp", "whatapp", "whats app", "wa"),
    "linkedin": ("linkedin", "linked in", "linkdin", "likendin"),
    "create_google_sheets": ("sheet", "sheets", "spreadsheet"),
    "create_google_docs": ("doc", "docs", "document"),
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
    "slack_send_message": "Slack",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "linkedin": "LinkedIn",
    "create_google_sheets": "Google Sheets",
    "create_google_docs": "Google Docs",
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
        "description": "Starts a workflow from another workflow execution context.",
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
    "create_google_docs": {
        "category": "action",
        "description": "Creates a Google Doc using a Docs credential.",
        "rules": [
            "Use config keys: credential_id, title, initial_content.",
            "credential_id must point to app_credentials with app_name=docs.",
            "title is required. initial_content is optional.",
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
        "description": "Conditional branch node. Output branches are true and false.",
        "rules": [
            "Use config keys: field, operator, value, value_mode, value_field, case_sensitive.",
            f"operator must be one of: {', '.join(SHARED_OPERATORS)}.",
            "Set value_mode=literal to compare against value, or value_mode=field to compare against value_field.",
            "case_sensitive applies to equals/not_equals/contains/not_contains and defaults to true.",
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
            "Use config keys: amount, unit, until_datetime.",
            "Preferred unit values: seconds, minutes, hours, days, months.",
            "until_datetime is optional ISO datetime and overrides amount/unit when provided.",
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
                definition, suggested_name = self.validate_generated_workflow(
                    raw_content,
                    user_prompt=cleaned_prompt,
                )
                if not suggested_name:
                    suggested_name = self._derive_workflow_name(cleaned_prompt)
                return GeneratedWorkflowResult(definition=definition, name=suggested_name)
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

        prompt_with_choices = self._merge_confirmed_choices_into_prompt(
            cleaned_prompt,
            confirmed_choices=confirmed_choices,
        )
        direct_question_prompt = prompt_with_choices
        prompt_with_choices = self._append_recent_chat_context_to_prompt(
            prompt_with_choices,
            recent_messages=recent_messages,
        )
        if normalized_interaction_mode == "ask":
            assistant_message = await self._answer_autoflow_question(
                prompt_with_choices,
                current_definition=current_definition,
                question_text=direct_question_prompt,
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

        inferred_trigger = cls._infer_trigger_type_from_prompt(prompt)
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
            - Avoid repeating the same generic brief when the user asks a specific follow-up.
            - Do not use markdown bold markers like * or ** in your response.
            - Always answer the latest user question first. Do not let older context override the current question intent.
            - If the question is about one node (for example http_request), focus on that node only and explain exactly what to send and where.
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
        current_definition: WorkflowDefinition,
    ) -> str:
        summary = cls._build_definition_summary(current_definition)
        return (
            f"User question:\n{prompt}\n\n"
            f"Current workflow context:\n{summary}\n\n"
            "Answer specifically in context of this current workflow where relevant."
        )

    async def _answer_autoflow_question(
        self,
        prompt: str,
        *,
        current_definition: WorkflowDefinition | None = None,
        question_text: str | None = None,
    ) -> str:
        cleaned_prompt = str(prompt or "").strip()
        if not cleaned_prompt:
            return "Please share your Autoflow question, and I can guide you step-by-step."
        latest_question = " ".join(str(question_text or cleaned_prompt).split()).strip()

        local_fallback = self._build_local_ask_response(
            prompt=latest_question,
            current_definition=current_definition,
        )

        try:
            client = self._get_client()
            system_prompt = self._build_ask_system_prompt()
            ask_temperature = self._default_temperature_for_model(self.model)
            user_prompt = cleaned_prompt
            if current_definition is not None:
                user_prompt = self._build_ask_user_prompt(
                    prompt=cleaned_prompt,
                    current_definition=current_definition,
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
                    return self._clip_assistant_message(
                        self._sanitize_ask_response_format(normalized_answer)
                    )
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
                return self._clip_assistant_message(
                    self._sanitize_ask_response_format(normalized_answer)
                )
        except Exception:
            return local_fallback
        return local_fallback

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
    def _build_local_ask_response(
        cls,
        *,
        prompt: str,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lowered = prompt.lower()
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
        node_focus = cls._infer_node_focus_from_prompt(
            lowered,
            current_definition=current_definition,
        )
        workflow_context_requested = "workflow" in lowered or "this flow" in lowered

        if wants_implementation_guide and node_focus != "http_request":
            return cls._clip_assistant_message(
                cls._build_routing_implementation_response(
                    definition=current_definition,
                    include_brief=wants_brief,
                )
            )
        if node_focus:
            return cls._clip_assistant_message(
                cls._build_node_focus_response(
                    node_type=node_focus,
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
            lines = [
                "I can help in Ask mode with:",
                "- Choosing the right trigger (manual/form/webhook/schedule/workflow trigger).",
                "- Explaining any node parameter and what each field does.",
                "- Recommending node combinations for your use case.",
                "- Showing how to map dynamic values with {{...}} templates.",
                "Share your goal or node name, and I will give direct Autoflow-specific guidance.",
            ]

        return cls._clip_assistant_message("\n".join(lines))

    @classmethod
    def _infer_node_focus_from_prompt(
        cls,
        lowered_prompt: str,
        *,
        current_definition: WorkflowDefinition | None = None,
    ) -> str | None:
        prompt = f" {lowered_prompt} "
        if current_definition is not None:
            for node in current_definition.nodes:
                node_id = str(node.id or "").strip().lower()
                node_label = str(node.label or "").strip().lower()
                if node_id and f" {node_id} " in prompt:
                    return node.type
                if node_label and f" {node_label} " in prompt:
                    return node.type

        manual_aliases: dict[str, tuple[str, ...]] = {
            "http_request": ("http node", "api node"),
            "send_gmail_message": ("gmail node", "email node"),
            "search_update_google_sheets": ("google sheets node", "sheets node", "sheet node"),
            "webhook_trigger": ("webhook", "webhook trigger"),
            "form_trigger": ("form trigger", "form submission node"),
            "schedule_trigger": ("schedule trigger", "cron trigger"),
            "manual_trigger": ("manual trigger", "run trigger"),
            "if_else": ("if else",),
            "ai_agent": ("ai node", "ai agent"),
            "image_gen": ("image node", "image generation node"),
        }

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
            for extra in manual_aliases.get(node_type, ()):
                aliases.add(str(extra).strip().lower())

            best_for_type = 0
            for alias in aliases:
                normalized_alias = f" {alias.strip()} "
                if len(normalized_alias.strip()) < 3:
                    continue
                if normalized_alias in prompt:
                    score = len(normalized_alias.strip().split())
                    best_for_type = max(best_for_type, score)
            if best_for_type > 0:
                scored_matches.append((best_for_type, len(raw), node_type))

        if scored_matches:
            scored_matches.sort(reverse=True)
            return scored_matches[0][2]
        return None

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
            f"Node: {node_type}",
            f"What it does: {description}",
        ]
        if isinstance(defaults, Mapping):
            config_keys = ", ".join(sorted(defaults.keys()))
            lines.append(f"Key parameters: {config_keys or 'No config keys'}")
        if rules:
            lines.append("How to use:")
            for index, rule in enumerate(rules[:4], start=1):
                lines.append(f"{index}. {rule}")

        if current_definition is not None:
            matching_nodes = [node for node in current_definition.nodes if node.type == node_type]
            if matching_nodes:
                lines.append("In your current workflow:")
                for node in matching_nodes[:3]:
                    lines.append(f"- {node.label} ({node.id}) is present.")
            else:
                lines.append("In your current workflow: this node is not present yet.")
        return "\n".join(lines)

    @classmethod
    def _build_http_node_response(
        cls,
        *,
        current_definition: WorkflowDefinition | None,
    ) -> str:
        lines = [
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
            http_nodes = [node for node in current_definition.nodes if node.type == "http_request"]
            if http_nodes:
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
            else:
                lines.append("In this workflow, no `http_request` node is present yet.")
                lines.append("Placement tip: add it after data preparation/classification and before final notification nodes.")

            webhook_nodes = [node for node in current_definition.nodes if node.type == "webhook_trigger"]
            if webhook_nodes:
                lines.append("Because your flow starts with webhook_trigger:")
                lines.append("- External client sends data to your webhook URL.")
                lines.append("- Then workflow can forward transformed data to external API via `http_request`.")

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
        lines.append("Where to place it:")
        lines.append(f"- {placement_text}")

        lines.append("Implementation Steps:")
        lines.append("1. Add an `if_else` node right after AI output is available (before final delivery nodes).")
        lines.append("2. Configure condition on a routing field, for example `output.sentiment` or `priority`.")
        lines.append("3. Wire `true` branch to urgent/high-priority path and `false` branch to normal path.")
        lines.append("4. If you need 3+ categories, replace `if_else` with `switch` and create one case per route.")
        lines.append("5. Ensure every branch ends in required actions (save/log/notify), then optionally merge branches.")

        lines.append("if_else parameters (example):")
        lines.append('```json\n{"field":"output.sentiment","operator":"equals","value":"negative","value_mode":"literal","value_field":"","case_sensitive":false}\n```')

        lines.append("switch parameters (example):")
        lines.append('```json\n{"field":"output.category","cases":[{"id":"billing_case","label":"Billing","operator":"equals","value":"billing"},{"id":"technical_case","label":"Technical","operator":"equals","value":"technical"}],"default_case":"general_case"}\n```')

        lines.append("Branch wiring:")
        lines.append("- `if_else`: outgoing edges must use `branch: \"true\"` and `branch: \"false\"`.")
        lines.append("- `switch`: outgoing edges must use `branch` equal to each case `id` (or `default_case`).")
        return "\n".join(lines)

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
        trigger_type = next(
            (node.type for node in definition.nodes if node.type in TRIGGER_NODE_TYPES),
            "manual_trigger",
        )
        main_steps = [
            cls._humanize_node_type(node.type)
            for node in definition.nodes
            if node.type not in TRIGGER_NODE_TYPES and node.type not in AI_CHAT_MODEL_NODE_TYPES
        ]
        rendered_steps = ", ".join(main_steps[:5]) if main_steps else "No downstream action nodes yet"

        points = [
            f"This workflow has {node_count} nodes and {edge_count} edges.",
            f"Start trigger is `{trigger_type}`.",
            f"Main path: {rendered_steps}.",
        ]
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
            2. an object with "definition" and optional "name" keys where definition is the workflow and name is the workflow title.

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
            {validation_suffix}
            """
        ).strip()

    @classmethod
    def validate_generated_workflow(
        cls,
        raw_content: str,
        *,
        user_prompt: str | None = None,
    ) -> tuple[WorkflowDefinition, str | None]:
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
        return definition, cls._extract_workflow_name(payload)

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

        preferred_trigger_type = cls._infer_trigger_type_from_prompt(prompt_text)
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
        field_catalog: list[tuple[str, str, str]] = [
            ("name", "Full Name", "text"),
            ("email", "Email", "email"),
            ("phone", "Phone", "text"),
            ("company", "Company", "text"),
            ("message", "Message", "textarea"),
            ("title", "Title", "text"),
        ]
        keyword_aliases: dict[str, tuple[str, ...]] = {
            "name": ("name", "full name"),
            "email": ("email", "e-mail"),
            "phone": ("phone", "mobile", "contact number", "whatsapp number"),
            "company": ("company", "organization"),
            "message": ("message", "feedback", "comment", "query", "question"),
            "title": ("title", "subject"),
        }

        inferred_fields: list[dict[str, Any]] = []
        for field_name, field_label, field_type in field_catalog:
            aliases = keyword_aliases.get(field_name, (field_name,))
            if any(alias in lowered for alias in aliases):
                inferred_fields.append(
                    {
                        "name": field_name,
                        "label": field_label,
                        "type": field_type,
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
            unit = str(node.config.get("unit") or "").strip().lower()
            if unit and unit not in allowed_units:
                raise WorkflowGenerationError(
                    f"Delay node '{node.id}' has unsupported unit '{unit}'. "
                    "Use seconds, minutes, hours, days, or months."
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
