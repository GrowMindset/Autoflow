"""Shared Gmail runner helpers."""

from __future__ import annotations

import json
from typing import Any

from googleapiclient.errors import HttpError


GMAIL_SEND_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]
GMAIL_MODIFY_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]


def extract_google_error(exc: HttpError) -> str:
    try:
        raw = exc.content.decode("utf-8", "ignore")
        payload = json.loads(raw)
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                message = str(err.get("message") or "").strip()
                status = str(err.get("status") or "").strip()
                if message and status:
                    return f"{status}: {message}"
                if message:
                    return message
        return raw or str(exc)
    except Exception:
        return str(exc)


def resolve_gmail_credential_data(
    config: dict[str, Any],
    context: dict[str, Any],
    *,
    integration_name: str,
) -> dict[str, Any]:
    cred_id = config.get("credential_id")
    if not cred_id:
        raise ValueError(f"{integration_name}: 'credential_id' is required.")

    all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
    raw_data = all_credential_data.get(str(cred_id))
    if not isinstance(raw_data, dict):
        raise ValueError(
            f"{integration_name}: Credential data not found. Save a Gmail credential and select it in this node."
        )
    return raw_data
