"""Telegram message runner — sends a real message via the Telegram Bot API.

Credential resolution
---------------------
The ``execute_workflow`` task pre-resolves every ``credential_id`` found in node
configs and stores them in:
- ``runner_context["resolved_credentials"]``       : ``str(credential_id) → api_key``
- ``runner_context["resolved_credential_data"]``   : ``str(credential_id) → token_data``

This runner reads bot token + chat id from credential data when possible, with
legacy config-field fallback for backward compatibility.

Config keys
-----------
- ``chat_id``       : str — Optional legacy override. Preferred source is credential token_data.chat_id.
- ``message``       : str — Text to send. Supports ``{{ }}`` template expressions.
- ``credential_id`` : str — UUID of an ``app_credentials`` row (app_name="telegram").
- ``bot_token``     : str — Optional legacy override; skips credential lookup if set.
- ``parse_mode``    : str — Optional parse mode: "HTML", "Markdown", or "MarkdownV2".
- ``image``         : str — Optional base64 image or data URI. Sends via sendPhoto.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx


TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramRunner:
    """Sends a message through the Telegram Bot API."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}

        # ── Resolve bot token ────────────────────────────────────────────────
        cred_id = config.get("credential_id")
        credential_data = {}
        if cred_id:
            all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
            raw_data = all_credential_data.get(str(cred_id))
            if isinstance(raw_data, dict):
                credential_data = raw_data

        bot_token = (
            config.get("bot_token")
            or credential_data.get("bot_token")
            or credential_data.get("api_key")
        )
        if not bot_token and cred_id:
            resolved: dict[str, str] = context.get("resolved_credentials") or {}
            bot_token = resolved.get(str(cred_id))
        if not bot_token:
            raise ValueError(
                "Telegram: No bot token available. "
                "Add a credential (app_name='telegram') with "
                'token_data = {"api_key": "<your-bot-token>", "chat_id": "<target-chat-id>"} '
                "and set the credential_id on the node config."
            )

        # ── Read message parameters ─────────────────────────────────────────
        chat_id = config.get("chat_id") or credential_data.get("chat_id") or ""
        message = str(config.get("message") or "")
        image = str(config.get("image") or "").strip()

        if not chat_id:
            raise ValueError(
                "Telegram: Chat ID is missing. "
                "Set token_data.chat_id in the selected credential or provide legacy chat_id in node config."
            )
        if not message and not image:
            raise ValueError("Telegram: provide either 'message' or 'image'.")

        parse_mode = config.get("parse_mode")

        # ── Call the Telegram Bot API ────────────────────────────────────────
        try:
            if image:
                response_data = self._send_photo(
                    bot_token=bot_token,
                    chat_id=chat_id,
                    image=image,
                    caption=message,
                    parse_mode=parse_mode,
                )
            else:
                response_data = self._send_message(
                    bot_token=bot_token,
                    chat_id=chat_id,
                    message=message,
                    parse_mode=parse_mode,
                )
        except Exception as exc:
            raise ValueError(f"Telegram: Failed to send message — {exc}") from exc

        # ── Build output ─────────────────────────────────────────────────────
        # Forward clean upstream data, stripping dummy runner artifacts and
        # internal execution fields that should not leak into outputs.
        _STRIP_PREFIXES = ("dummy_node_",)
        _STRIP_KEYS = {"_branch", "_split_index"}

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            for key, value in input_data.items():
                if key in _STRIP_KEYS:
                    continue
                if any(key.startswith(prefix) for prefix in _STRIP_PREFIXES):
                    continue
                result[key] = value

        result["telegram_sent"] = True
        result["telegram_response"] = response_data
        result["telegram_chat_id"] = chat_id
        result["telegram_message"] = message
        result["telegram_sent_photo"] = bool(image)
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _send_message(
        *,
        bot_token: str,
        chat_id: str,
        message: str,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """POST to Telegram's sendMessage endpoint (sync-safe)."""
        url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": message,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        def _do_request() -> dict[str, Any]:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                body = resp.json()

            if not body.get("ok"):
                description = body.get("description", "Unknown Telegram error")
                raise ValueError(f"Telegram API error: {description}")

            return body.get("result", body)

        # Handle both sync and async contexts (same pattern as AIAgentRunner).
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _do_request()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_request)
            return future.result()

    @staticmethod
    def _send_photo(
        *,
        bot_token: str,
        chat_id: str,
        image: str,
        caption: str = "",
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """POST to Telegram's sendPhoto endpoint with an uploaded image file."""
        image_bytes, mime_type = TelegramRunner._decode_image(image)
        url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendPhoto"
        payload: dict[str, Any] = {"chat_id": chat_id}
        if caption:
            payload["caption"] = caption
        if parse_mode:
            payload["parse_mode"] = parse_mode
        files = {"photo": ("autoflow-image.png", image_bytes, mime_type)}

        def _do_request() -> dict[str, Any]:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, data=payload, files=files)
                resp.raise_for_status()
                body = resp.json()

            if not body.get("ok"):
                description = body.get("description", "Unknown Telegram error")
                raise ValueError(f"Telegram API error: {description}")

            return body.get("result", body)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _do_request()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_request)
            return future.result()

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
            return base64.b64decode(raw, validate=True), mime_type
        except Exception as exc:
            raise ValueError("Image field must resolve to valid base64 image data.") from exc
