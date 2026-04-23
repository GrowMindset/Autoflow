from __future__ import annotations

import re
from typing import Any


_UNSUPPORTED_MAX_TOKENS_PATTERN = re.compile(
    r"unsupported parameter:\s*'max_tokens'.*max_completion_tokens",
    flags=re.IGNORECASE | re.DOTALL,
)
_LOOP_NODE_CAP_PATTERN = re.compile(
    r"Loop safety cap reached for node\s+'([^']+)':\s*max_node_executions=(\d+)",
    flags=re.IGNORECASE,
)
_LOOP_TOTAL_CAP_PATTERN = re.compile(
    r"max_total_node_executions=(\d+)",
    flags=re.IGNORECASE,
)
_SUBNODE_FAILURE_PATTERN = re.compile(
    r"Sub-node\s+'([^']+)'\s+\(([^)]+)\)\s+failed:\s*(.+)",
    flags=re.IGNORECASE | re.DOTALL,
)
_PREFIX_PATTERN = re.compile(
    r"^(?:ValueError|RuntimeError|Exception|KeyError|TypeError|AssertionError):\s*",
    flags=re.IGNORECASE,
)
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _clean_raw_message(raw: str) -> str:
    message = str(raw or "").strip()
    if not message:
        return ""
    message = _PREFIX_PATTERN.sub("", message)
    message = message.replace("\r", " ").replace("\n", " ")
    message = _WHITESPACE_PATTERN.sub(" ", message).strip()
    return message


def to_user_friendly_error_message(
    error: Any,
    *,
    node_type: str | None = None,
    fallback: str = "Something went wrong while running this step.",
) -> str:
    raw = _clean_raw_message(str(error or ""))
    if not raw:
        return fallback

    lower = raw.lower()

    if _UNSUPPORTED_MAX_TOKENS_PATTERN.search(raw):
        return (
            "This model expects max completion tokens instead of max tokens. "
            "Please retry the workflow."
        )

    if "no api key found for credential_id" in lower:
        return (
            "Missing AI credential. Connect a valid Chat Model credential and try again."
        )

    if "invalid api key" in lower or "unauthorized" in lower or "status code: 401" in lower:
        return "Authentication failed. Reconnect your credential and try again."

    if "forbidden" in lower or "status code: 403" in lower:
        return "Permission denied for this action. Check the account access and permissions."

    if "rate limit" in lower or "too many requests" in lower or "status code: 429" in lower:
        return "Rate limit reached. Please wait a moment and retry."

    if "timed out" in lower or "timeout" in lower:
        return "The request timed out. Please retry."

    if "credential_id" in lower and "required" in lower:
        return "Missing credential. Open this node and select the required credential."

    if "could not resolve host" in lower:
        return "Could not reach the target host. Check the URL/domain and try again."

    if "connection refused" in lower or "failed to establish a new connection" in lower:
        return "Could not connect to the target service. Verify the service is reachable."

    if "outbound requests to localhost/private networks are blocked" in lower:
        return (
            "This URL points to a local or private network, which is blocked for security."
        )

    if "no celery worker is consuming queue" in lower:
        return "No worker is available to run this workflow right now. Start a worker and try again."

    if "failed to enqueue background task" in lower:
        return "Could not start background execution. Please ensure workers are running and retry."

    if "model" in lower and "not found" in lower:
        return "The selected model is unavailable. Choose a valid model and retry."

    loop_node_match = _LOOP_NODE_CAP_PATTERN.search(raw)
    if loop_node_match:
        node_id = loop_node_match.group(1)
        limit = loop_node_match.group(2)
        return (
            f"Loop limit reached for node '{node_id}' (max {limit} runs). "
            "Increase loop limits or adjust loop conditions."
        )

    if "workflow stopped due to loop safety cap" in lower:
        total_match = _LOOP_TOTAL_CAP_PATTERN.search(raw)
        limit_info = (
            f" (max total runs: {total_match.group(1)})" if total_match else ""
        )
        return (
            "Workflow stopped to prevent an infinite loop"
            f"{limit_info}. Increase loop limits or adjust loop conditions."
        )

    if "all incoming branches were blocked" in lower:
        return "No branch produced data for this step."

    if "waiting for remaining unblocked inputs" in lower:
        return "Waiting for other required branch inputs."

    subnode_match = _SUBNODE_FAILURE_PATTERN.search(raw)
    if subnode_match:
        subnode_id = subnode_match.group(1)
        inner_message = _clean_raw_message(subnode_match.group(3))
        if not inner_message:
            inner_message = "Sub-node failed to run."
        return f"Linked node '{subnode_id}' failed: {inner_message}"

    provider_prefixes: dict[str, str] = {
        "http request:": "HTTP request failed: ",
        "gmail send:": "Gmail step failed: ",
        "gmail get:": "Gmail step failed: ",
        "google sheets:": "Google Sheets step failed: ",
        "google docs:": "Google Docs step failed: ",
        "telegram:": "Telegram step failed: ",
        "whatsapp:": "WhatsApp step failed: ",
        "linkedin:": "LinkedIn step failed: ",
        "slack:": "Slack step failed: ",
        "ai agent:": "AI step failed: ",
    }
    for prefix, replacement in provider_prefixes.items():
        if lower.startswith(prefix):
            return replacement + raw[len(prefix):].strip()

    if node_type and raw == str(node_type):
        return fallback

    return raw
