"""Gmail send runner using Google OAuth credentials."""

from __future__ import annotations

import base64
import re
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential
from .gmail_common import GMAIL_SEND_SCOPES, extract_google_error, resolve_gmail_credential_data


EMAIL_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*.+?\s*\}\}")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_LIKE_DICT_KEYS = (
    "email",
    "to",
    "address",
    "recipient",
    "recipient_email",
    "user_email",
)


class SendGmailMessageRunner:
    """Sends an email through Gmail."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        credential_data = resolve_gmail_credential_data(config, context, integration_name="Gmail Send")

        to_list = self._split_and_validate_emails(config.get("to"), field_name="to")
        cc_list = self._split_and_validate_emails(config.get("cc"), field_name="cc")
        bcc_list = self._split_and_validate_emails(config.get("bcc"), field_name="bcc")
        reply_to = self._normalize_single_email(config.get("reply_to"), field_name="reply_to")
        subject = str(config.get("subject") or "").strip()
        body = str(config.get("body") or "")
        image = str(config.get("image") or "").strip()
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
        if image:
            image_bytes, image_subtype = self._decode_image(image)
            message.add_attachment(
                image_bytes,
                maintype="image",
                subtype=image_subtype,
                filename="image.png",
            )

        if not is_google_oauth_credential(credential_data):
            raise ValueError(
                "Gmail Send: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        api_response = self._send_via_gmail_api(
            credential_data=credential_data,
            message=message,
        )
        message_id = str(api_response.get("id") or "").strip()

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
                "gmail_attached_image": bool(image),
                "message_id": message_id,
                "gmail_message_id": message_id,
            }
        )
        return result

    def _send_via_gmail_api(
        self,
        *,
        credential_data: dict[str, Any],
        message: EmailMessage,
    ) -> dict[str, Any]:
        credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GMAIL_SEND_SCOPES,
            integration_name="Gmail Send",
        )
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        try:
            response = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
            return response if isinstance(response, dict) else {}
        except RefreshError as exc:
            raise ValueError(
                "Gmail Send: OAuth token refresh failed. Reconnect Google OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = extract_google_error(exc)
            if "invalid to header" in google_error.lower():
                raise ValueError(
                    "Gmail Send: Invalid recipient in 'to'. "
                    "Use valid email(s), comma-separated (for example: user@example.com). "
                    "If you're using a template, make sure it resolves to a real email."
                ) from exc
            raise ValueError(f"Gmail Send: Gmail API send failed: {google_error}") from exc

    @staticmethod
    def _normalize_single_email(value: Any, field_name: str) -> str:
        emails = SendGmailMessageRunner._split_and_validate_emails(value, field_name=field_name)
        if not emails:
            return ""
        if len(emails) > 1:
            raise ValueError(
                f"Gmail Send: '{field_name}' must contain only one email address."
            )
        return emails[0]

    @staticmethod
    def _split_and_validate_emails(value: Any, field_name: str) -> list[str]:
        if value is None:
            return []

        raw_chunks = SendGmailMessageRunner._flatten_email_candidates(value)
        candidates: list[str] = []
        for chunk in raw_chunks:
            normalized_chunk = chunk.replace(";", ",").replace("\n", ",").replace("\r", ",")
            candidates.extend(
                item.strip()
                for item in normalized_chunk.split(",")
                if item and item.strip()
            )
        if not candidates:
            return []

        normalized: list[str] = []
        invalid: list[str] = []
        unresolved: list[str] = []

        for candidate in candidates:
            if EMAIL_PLACEHOLDER_PATTERN.search(candidate):
                unresolved.append(candidate)
                continue

            _name, parsed_email = parseaddr(candidate)
            email_value = (parsed_email or candidate).strip().strip("<>").strip()
            if not email_value:
                continue

            if not SendGmailMessageRunner._is_valid_email(email_value):
                invalid.append(candidate)
                continue

            normalized.append(email_value)

        if unresolved:
            raise ValueError(
                f"Gmail Send: '{field_name}' contains unresolved template value(s): "
                + ", ".join(unresolved)
            )
        if invalid:
            raise ValueError(
                f"Gmail Send: '{field_name}' contains invalid email address(es): "
                + ", ".join(invalid)
            )
        return normalized

    @staticmethod
    def _flatten_email_candidates(value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            return [value]

        if isinstance(value, (list, tuple, set)):
            flattened: list[str] = []
            for item in value:
                flattened.extend(SendGmailMessageRunner._flatten_email_candidates(item))
            return flattened

        if isinstance(value, dict):
            for key in EMAIL_LIKE_DICT_KEYS:
                if key in value and value[key] is not None:
                    return SendGmailMessageRunner._flatten_email_candidates(value[key])

            # Fall back to direct scalar values for single-entry dicts.
            if len(value) == 1:
                only_value = next(iter(value.values()))
                return SendGmailMessageRunner._flatten_email_candidates(only_value)

            return [str(value)]

        return [str(value)]

    @staticmethod
    def _is_valid_email(value: str) -> bool:
        return bool(EMAIL_PATTERN.match(value))

    @staticmethod
    def _decode_image(value: str) -> tuple[bytes, str]:
        raw = str(value or "").strip()
        mime_type = "image/png"
        if raw.startswith("data:"):
            header, _, body = raw.partition(",")
            if ";base64" in header and header.startswith("data:"):
                mime_type = header[5:].split(";", 1)[0] or mime_type
            raw = body
        try:
            image_bytes = base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise ValueError(
                "Gmail Send: image field must resolve to valid base64 image data."
            ) from exc
        subtype = mime_type.split("/", 1)[1] if "/" in mime_type else "png"
        return image_bytes, subtype
