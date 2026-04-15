"""Gmail fetch runner using Google OAuth credentials."""

from __future__ import annotations

import base64
import email
from email import policy
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential


GMAIL_READ_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GetGmailMessageRunner:
    """Fetches recent Gmail messages from a mailbox folder."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        credential_data = self._resolve_credential_data(config, context)

        folder = str(config.get("folder") or "INBOX")
        query = str(config.get("query") or "").strip()
        limit = self._parse_limit(config.get("limit"))
        unread_only = bool(config.get("unread_only", False))
        include_body = bool(config.get("include_body", False))
        mark_as_read = bool(config.get("mark_as_read", False))
        if not is_google_oauth_credential(credential_data):
            raise ValueError(
                "Gmail Get: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        messages = self._fetch_via_gmail_api(
            credential_data=credential_data,
            folder=folder,
            query=query,
            limit=limit,
            unread_only=unread_only,
            include_body=include_body,
            mark_as_read=mark_as_read,
        )

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)
        result.update(
            {
                "gmail_messages": messages,
                "gmail_message_count": len(messages),
                "gmail_folder": folder,
                "gmail_query": query,
                "gmail_unread_only": unread_only,
            }
        )
        return result

    def _fetch_via_gmail_api(
        self,
        *,
        credential_data: dict[str, Any],
        folder: str,
        query: str,
        limit: int,
        unread_only: bool,
        include_body: bool,
        mark_as_read: bool,
    ) -> list[dict[str, Any]]:
        credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GMAIL_READ_SCOPES,
            integration_name="Gmail Get",
        )
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)

        q_parts: list[str] = []
        if query:
            q_parts.append(query)
        if unread_only:
            q_parts.append("is:unread")
        q_value = " ".join(q_parts).strip()

        list_kwargs: dict[str, Any] = {
            "userId": "me",
            "maxResults": limit,
        }
        if q_value:
            list_kwargs["q"] = q_value
        normalized_folder = folder.strip().upper()
        if normalized_folder and normalized_folder != "ALL":
            list_kwargs["labelIds"] = [normalized_folder]

        try:
            list_response = service.users().messages().list(**list_kwargs).execute()
        except RefreshError as exc:
            raise ValueError(
                "Gmail Get: OAuth token refresh failed. Reconnect Google OAuth credential."
            ) from exc
        except HttpError as exc:
            raise ValueError(f"Gmail Get: Gmail API list failed: {exc}") from exc

        messages: list[dict[str, Any]] = []
        for item in list_response.get("messages", []) or []:
            message_id = str(item.get("id") or "")
            if not message_id:
                continue
            try:
                detail = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute()
                )
            except HttpError:
                continue

            headers = self._header_map((detail.get("payload") or {}).get("headers") or [])
            body_text = self._extract_gmail_payload_text(detail.get("payload") or {})

            message_item = {
                "id": message_id,
                "from": headers.get("from", ""),
                "to": headers.get("to", ""),
                "subject": headers.get("subject", ""),
                "date": headers.get("date", ""),
                "message_id": headers.get("message-id", ""),
                "snippet": str(detail.get("snippet") or body_text[:240]),
            }
            if include_body:
                message_item["body"] = body_text
            messages.append(message_item)

            if mark_as_read:
                try:
                    (
                        service.users()
                        .messages()
                        .modify(
                            userId="me",
                            id=message_id,
                            body={"removeLabelIds": ["UNREAD"]},
                        )
                        .execute()
                    )
                except HttpError:
                    pass

        return messages

    @staticmethod
    def _parse_limit(raw_limit: Any) -> int:
        try:
            value = int(str(raw_limit or "10"))
        except Exception:
            value = 10
        return min(max(value, 1), 100)

    @staticmethod
    def _extract_email_body_text(message: Any) -> str:
        if message.is_multipart():
            # Prefer plain text parts first.
            for part in message.walk():
                content_type = (part.get_content_type() or "").lower()
                disposition = str(part.get("Content-Disposition") or "").lower()
                if "attachment" in disposition:
                    continue
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")

            # Fallback to any text part.
            for part in message.walk():
                content_type = (part.get_content_type() or "").lower()
                if content_type.startswith("text/"):
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
            return ""

        payload = message.get_payload(decode=True)
        if payload is None:
            return str(message.get_payload() or "")
        charset = message.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    @staticmethod
    def _header_map(headers: list[dict[str, Any]]) -> dict[str, str]:
        result: dict[str, str] = {}
        for header in headers:
            if not isinstance(header, dict):
                continue
            name = str(header.get("name") or "").strip().lower()
            value = str(header.get("value") or "")
            if name:
                result[name] = value
        return result

    @classmethod
    def _extract_gmail_payload_text(cls, payload: dict[str, Any]) -> str:
        body_data = (
            (payload.get("body") or {}).get("data")
            if isinstance(payload.get("body"), dict)
            else None
        )
        if isinstance(body_data, str) and body_data:
            decoded = cls._decode_gmail_base64(body_data)
            if decoded:
                return decoded

        for part in payload.get("parts", []) or []:
            if not isinstance(part, dict):
                continue
            mime = str(part.get("mimeType") or "").lower()
            if mime == "text/plain":
                part_data = (part.get("body") or {}).get("data")
                decoded = cls._decode_gmail_base64(part_data)
                if decoded:
                    return decoded

        for part in payload.get("parts", []) or []:
            if not isinstance(part, dict):
                continue
            decoded = cls._extract_gmail_payload_text(part)
            if decoded:
                return decoded
        return ""

    @staticmethod
    def _decode_gmail_base64(value: Any) -> str:
        if not isinstance(value, str) or not value:
            return ""
        try:
            padded = value + ("=" * ((4 - len(value) % 4) % 4))
            raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _resolve_credential_data(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cred_id = config.get("credential_id")
        if not cred_id:
            raise ValueError("Gmail Get: 'credential_id' is required.")

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        raw_data = all_credential_data.get(str(cred_id))
        if not isinstance(raw_data, dict):
            raise ValueError(
                "Gmail Get: Credential data not found. Save a Gmail credential and select it in this node."
            )
        return raw_data
