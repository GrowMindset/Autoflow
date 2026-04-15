"""Gmail send runner using Google OAuth credentials."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential


GMAIL_SEND_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]


class SendGmailMessageRunner:
    """Sends an email through Gmail."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        credential_data = self._resolve_credential_data(config, context)

        to_list = self._split_emails(config.get("to"))
        cc_list = self._split_emails(config.get("cc"))
        bcc_list = self._split_emails(config.get("bcc"))
        reply_to = str(config.get("reply_to") or "").strip()
        subject = str(config.get("subject") or "").strip()
        body = str(config.get("body") or "")
        is_html = bool(config.get("is_html", False))

        if not to_list:
            raise ValueError("Gmail Send: 'to' is required.")
        if not subject:
            raise ValueError("Gmail Send: 'subject' is required.")
        if not body:
            raise ValueError("Gmail Send: 'body' is required.")

        sender_email = (
            str(credential_data.get("email") or credential_data.get("user_email") or credential_data.get("username") or "").strip()
        )
        message = EmailMessage()
        if sender_email:
            message["From"] = sender_email
        message["To"] = ", ".join(to_list)
        if cc_list:
            message["Cc"] = ", ".join(cc_list)
        if bcc_list:
            message["Bcc"] = ", ".join(bcc_list)
        if reply_to:
            message["Reply-To"] = reply_to
        message["Subject"] = subject
        if is_html:
            message.add_alternative(body, subtype="html")
        else:
            message.set_content(body)

        if not is_google_oauth_credential(credential_data):
            raise ValueError(
                "Gmail Send: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        self._send_via_gmail_api(
            credential_data=credential_data,
            message=message,
        )

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)
        result.update(
            {
                "gmail_sent": True,
                "gmail_sender": sender_email,
                "gmail_to": to_list,
                "gmail_cc": cc_list,
                "gmail_bcc": bcc_list,
                "gmail_subject": subject,
                "gmail_is_html": is_html,
            }
        )
        return result

    def _send_via_gmail_api(
        self,
        *,
        credential_data: dict[str, Any],
        message: EmailMessage,
    ) -> None:
        credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GMAIL_SEND_SCOPES,
            integration_name="Gmail Send",
        )
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        try:
            (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
        except RefreshError as exc:
            raise ValueError(
                "Gmail Send: OAuth token refresh failed. Reconnect Google OAuth credential."
            ) from exc
        except HttpError as exc:
            raise ValueError(f"Gmail Send: Gmail API send failed: {exc}") from exc

    @staticmethod
    def _split_emails(value: Any) -> list[str]:
        raw = str(value or "").replace(";", ",")
        emails = [item.strip() for item in raw.split(",")]
        return [item for item in emails if item]

    @staticmethod
    def _resolve_credential_data(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cred_id = config.get("credential_id")
        if not cred_id:
            raise ValueError("Gmail Send: 'credential_id' is required.")

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        raw_data = all_credential_data.get(str(cred_id))
        if not isinstance(raw_data, dict):
            raise ValueError(
                "Gmail Send: Credential data not found. Save a Gmail credential and select it in this node."
            )
        return raw_data
