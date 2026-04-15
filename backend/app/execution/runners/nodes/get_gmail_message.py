"""Gmail fetch runner using IMAP + app password credentials."""

from __future__ import annotations

import email
import imaplib
from email import policy
from typing import Any


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

        user_email = (
            credential_data.get("email")
            or credential_data.get("user_email")
            or credential_data.get("username")
            or ""
        )
        app_password = (
            credential_data.get("app_password")
            or credential_data.get("password")
            or credential_data.get("api_key")
            or ""
        )
        if not user_email:
            raise ValueError("Gmail Get: Email is missing in selected credential.")
        if not app_password:
            raise ValueError("Gmail Get: App password is missing in selected credential.")

        folder = str(config.get("folder") or "INBOX")
        query = str(config.get("query") or "").strip().lower()
        limit = self._parse_limit(config.get("limit"))
        unread_only = bool(config.get("unread_only", False))
        include_body = bool(config.get("include_body", False))
        mark_as_read = bool(config.get("mark_as_read", False))

        messages: list[dict[str, Any]] = []
        with imaplib.IMAP4_SSL("imap.gmail.com", 993) as mailbox:
            mailbox.login(user_email, app_password)

            status, _ = mailbox.select(folder, readonly=not mark_as_read)
            if status != "OK":
                raise ValueError(f"Gmail Get: Could not open folder '{folder}'.")

            criteria = ["UNSEEN"] if unread_only else ["ALL"]
            status, data = mailbox.search(None, *criteria)
            if status != "OK":
                raise ValueError("Gmail Get: Failed to search mailbox.")

            ids = data[0].split() if data and data[0] else []
            ids = list(reversed(ids))

            for raw_id in ids:
                if len(messages) >= limit:
                    break
                status, msg_data = mailbox.fetch(raw_id, "(RFC822)")
                if status != "OK" or not msg_data:
                    continue

                message_bytes = None
                for part in msg_data:
                    if isinstance(part, tuple) and len(part) >= 2:
                        message_bytes = part[1]
                        break
                if not message_bytes:
                    continue

                parsed = email.message_from_bytes(message_bytes, policy=policy.default)
                message_item = {
                    "id": raw_id.decode(errors="ignore"),
                    "from": str(parsed.get("From") or ""),
                    "to": str(parsed.get("To") or ""),
                    "subject": str(parsed.get("Subject") or ""),
                    "date": str(parsed.get("Date") or ""),
                    "message_id": str(parsed.get("Message-Id") or ""),
                }
                body_text = self._extract_body_text(parsed)
                message_item["snippet"] = body_text[:240]
                if include_body:
                    message_item["body"] = body_text

                # local query filter to support flexible search text
                if query:
                    haystack = " ".join(
                        [
                            message_item.get("from", ""),
                            message_item.get("to", ""),
                            message_item.get("subject", ""),
                            body_text,
                        ]
                    ).lower()
                    if query not in haystack:
                        continue

                messages.append(message_item)
                if mark_as_read:
                    mailbox.store(raw_id, "+FLAGS", "\\Seen")

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

    @staticmethod
    def _parse_limit(raw_limit: Any) -> int:
        try:
            value = int(str(raw_limit or "10"))
        except Exception:
            value = 10
        return min(max(value, 1), 100)

    @staticmethod
    def _extract_body_text(message: Any) -> str:
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
