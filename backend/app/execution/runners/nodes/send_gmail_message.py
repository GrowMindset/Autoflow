"""Gmail send runner using SMTP + app password credentials."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any


class SendGmailMessageRunner:
    """Sends an email through Gmail SMTP."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        credential_data = self._resolve_credential_data(config, context)

        sender_email = (
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
        if not sender_email:
            raise ValueError("Gmail Send: Sender email is missing in selected credential.")
        if not app_password:
            raise ValueError("Gmail Send: App password is missing in selected credential.")

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

        message = EmailMessage()
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

        recipients = to_list + cc_list + bcc_list
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(sender_email, app_password)
            smtp.send_message(message, from_addr=sender_email, to_addrs=recipients)

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

