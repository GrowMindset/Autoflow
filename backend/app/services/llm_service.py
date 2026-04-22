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
SEQUENCE_DAYS_PATTERN = re.compile(r"\b(\d{1,2})\s*-\s*day\b|\b(\d{1,2})\s*day\b")

TRIGGER_KEYWORD_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("workflow_trigger", ("workflow trigger", "from another workflow", "parent workflow")),
    ("form_trigger", ("form", "submission", "submit", "user input form")),
    ("webhook_trigger", ("webhook", "endpoint", "api call", "http request", "callback")),
    (
        "schedule_trigger",
        (
            "schedule",
            "cron",
            "hourly",
            "daily",
            "weekly",
            "monthly",
            "every ",
            "each day",
        ),
    ),
    ("manual_trigger", ("manual", "manually", "on demand", "run button")),
)

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
            "Use config keys: credential_id, to, cc, bcc, reply_to, subject, body, is_html.",
            "Use comma-separated emails in to/cc/bcc when multiple recipients are needed.",
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
            "Use config keys: credential_id, document_id, operation, text, match_text, match_case.",
            "operation must be append_text or replace_all_text.",
            "match_text is required when operation is replace_all_text.",
        ],
    },
    "telegram": {
        "category": "action",
        "description": "Sends a Telegram message. Use credential_id and message. The credential stores bot token + chat_id.",
        "rules": [
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
            "Use config keys: credential_id, post_text, visibility.",
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
            "When referencing upstream workflow data, use {{path.to.value}} templates.",
            "For form triggers, both {{field_name}} and {{form.field_name}} are supported.",
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
            - Use clear human-readable labels.
            - position.x and position.y must be numbers.
            - Always include a config object, even when it is empty.
            - For dummy integration nodes, keep unresolved user-specific values as empty strings instead of inventing secrets, ids, or credentials.
            - Never invent extra config keys that are not part of the schema below.
            - If you use ai_agent, also include exactly one connected chat_model_openai or chat_model_groq node for it.
            - Chat model nodes are configuration sub-nodes, not normal workflow steps.
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
            1. Pick the best trigger from the request intent.
            2. Include all necessary nodes to complete the business flow end-to-end.
            3. Fill node configs using the schema keys and realistic defaults/placeholders.
            4. Wire edges correctly, including branch labels for if_else/switch.
            5. If ai_agent exists, connect exactly one chat model sub-node to targetHandle "chat_model".
            6. Always use Autoflow template syntax {{...}} for dynamic values; do not use single braces.
            7. If the request specifies a multi-day sequence (for example 14-day), ensure cadence/timing truly matches that duration.
            8. For multi-channel nurture flows, branch channels in parallel rather than chaining all channels serially.
            9. Return only one JSON object; no explanation text.
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
        cls._validate_sequence_duration_expectation(definition, user_prompt=user_prompt)
        cls._validate_multi_channel_branching_expectation(definition, user_prompt=user_prompt)
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
        lowered = prompt.lower()
        for trigger_type, keywords in TRIGGER_KEYWORD_HINTS:
            if any(keyword in lowered for keyword in keywords):
                return trigger_type
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
        return 0.1

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
        if not any(token in prompt for token in ("branch", "parallel")):
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

    @staticmethod
    def _infer_requested_channel_node_types(prompt: str) -> set[str]:
        channel_map = {
            "send_gmail_message": ("email", "gmail", "mail"),
            "whatsapp": ("whatsapp", "wa"),
            "telegram": ("telegram",),
            "slack_send_message": ("slack",),
        }
        requested: set[str] = set()
        for node_type, tokens in channel_map.items():
            if any(token in prompt for token in tokens):
                requested.add(node_type)
        return requested

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
