"""Gmail draft creation runner using Google OAuth credentials."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .gmail_common import GMAIL_SEND_SCOPES, extract_google_error, resolve_gmail_credential_data
from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential
from .send_gmail_message import SendGmailMessageRunner


class CreateGmailDraftRunner:
    """Creates a Gmail draft."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        credential_data = resolve_gmail_credential_data(config, context, integration_name="Gmail Draft")

        to_list = SendGmailMessageRunner._split_and_validate_emails(config.get("to"), field_name="to")
        subject = str(config.get("subject") or "").strip()
        body = str(config.get("body") or "")

        if not to_list:
            raise ValueError("Gmail Draft: 'to' is required.")
        if not subject:
            raise ValueError("Gmail Draft: 'subject' is required.")
        if not body:
            raise ValueError("Gmail Draft: 'body' is required.")

        sender_email = str(
            credential_data.get("email")
            or credential_data.get("user_email")
            or credential_data.get("username")
            or ""
        ).strip()
        message = EmailMessage()
        if sender_email:
            message["From"] = sender_email
        message["To"] = ", ".join(to_list)
        message["Subject"] = subject
        message.set_content(body)

        if not is_google_oauth_credential(credential_data):
            raise ValueError(
                "Gmail Draft: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        draft = self._create_via_gmail_api(
            credential_data=credential_data,
            message=message,
        )
        draft_id = str(draft.get("id") or "").strip()

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)
        result.update(
            {
                "draft_id": draft_id,
                "gmail_draft_id": draft_id,
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
        return result

    def _create_via_gmail_api(
        self,
        *,
        credential_data: dict[str, Any],
        message: EmailMessage,
    ) -> dict[str, Any]:
        credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GMAIL_SEND_SCOPES,
            integration_name="Gmail Draft",
        )
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        try:
            response = (
                service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw}})
                .execute()
            )
            return response if isinstance(response, dict) else {}
        except RefreshError as exc:
            raise ValueError(
                "Gmail Draft: OAuth token refresh failed. Reconnect Google OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = extract_google_error(exc)
            if "invalid to header" in google_error.lower():
                raise ValueError(
                    "Gmail Draft: Invalid recipient in 'to'. Use valid email(s), comma-separated."
                ) from exc
            raise ValueError(f"Gmail Draft: Gmail API draft creation failed: {google_error}") from exc
