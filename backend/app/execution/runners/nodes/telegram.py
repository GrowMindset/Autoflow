"""Telegram message runner — sends a real message via the Telegram Bot API.

Credential resolution
---------------------
The ``execute_workflow`` task pre-resolves every ``credential_id`` found in node
configs into a decrypted API key/token and stores them in
``runner_context["resolved_credentials"]`` as  ``str(credential_id) → token``.

This runner reads the bot token from that dict (or falls back to a ``bot_token``
value injected directly into ``config`` for quick testing).

Config keys
-----------
- ``chat_id``       : str — Target Telegram chat / group / channel ID.
- ``message``       : str — Text to send. Supports ``{{ }}`` template expressions.
- ``credential_id`` : str — UUID of an ``app_credentials`` row (app_name="telegram").
- ``bot_token``     : str — Optional override; skips credential lookup if set.
- ``parse_mode``    : str — Optional parse mode: "HTML", "Markdown", or "MarkdownV2".
"""

from __future__ import annotations

import asyncio
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
        bot_token = config.get("bot_token")
        if not bot_token:
            cred_id = config.get("credential_id")
            resolved: dict[str, str] = context.get("resolved_credentials") or {}
            if cred_id:
                bot_token = resolved.get(str(cred_id))
            if not bot_token:
                raise ValueError(
                    "Telegram: No bot token available. "
                    "Add a credential (app_name='telegram') with "
                    "token_data = {\"api_key\": \"<your-bot-token>\"} and set "
                    "the credential_id on the node config."
                )

        # ── Read message parameters ─────────────────────────────────────────
        chat_id = config.get("chat_id", "")
        message = config.get("message", "")

        if not chat_id:
            raise ValueError("Telegram: 'chat_id' is required but was not set.")
        if not message:
            raise ValueError("Telegram: 'message' is required but was not set.")

        parse_mode = config.get("parse_mode")

        # ── Call the Telegram Bot API ────────────────────────────────────────
        try:
            response_data = self._send_message(
                bot_token=bot_token,
                chat_id=chat_id,
                message=message,
                parse_mode=parse_mode,
            )
        except Exception as exc:
            raise ValueError(f"Telegram: Failed to send message — {exc}") from exc

        # ── Build output ─────────────────────────────────────────────────────
        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)

        result["telegram_sent"] = True
        result["telegram_response"] = response_data
        result["telegram_chat_id"] = chat_id
        result["telegram_message"] = message
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
