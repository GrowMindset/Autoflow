"""Slack message runner — sends a real message via Slack Incoming Webhooks.

Credential resolution
---------------------
The ``execute_workflow`` task pre-resolves every ``credential_id`` found in node
configs and stores them in:
- ``runner_context["resolved_credentials"]``       : ``str(credential_id) → api_key``
- ``runner_context["resolved_credential_data"]``   : ``str(credential_id) → token_data``

This runner reads webhook_url + channel from credential data when possible, with
legacy config-field fallback for backward compatibility.

Config keys
-----------
- ``webhook_url``      : str — Optional legacy override. Preferred source is credential token_data.webhook_url.
- ``channel``          : str — Optional legacy override. Preferred source is credential token_data.channel.
- ``message``          : str — Text to send. Supports ``{{ }}`` template expressions.
- ``credential_id``    : str — UUID of an ``app_credentials`` row (app_name="slack").
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class SlackSendMessageRunner:
    """Sends a message through a Slack Incoming Webhook."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}

        cred_id = config.get("credential_id")
        credential_data: dict[str, Any] = {}
        if cred_id:
            all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
            raw_data = all_credential_data.get(str(cred_id))
            if isinstance(raw_data, dict):
                credential_data = raw_data

        webhook_url = (
            config.get("webhook_url")
            or credential_data.get("webhook_url")
            or credential_data.get("api_key")
        )
        if not webhook_url and cred_id:
            resolved: dict[str, str] = context.get("resolved_credentials") or {}
            webhook_url = resolved.get(str(cred_id))
        if not webhook_url:
            raise ValueError(
                "Slack: No webhook URL available. "
                "Add a credential (app_name='slack') with "
                "token_data = {\"webhook_url\": \"https://hooks.slack.com/services/T...\"} "
                "and set the credential_id on the node config."
            )
            
        webhook_url = webhook_url.strip()
        if not webhook_url.startswith("http://") and not webhook_url.startswith("https://"):
            webhook_url = f"https://{webhook_url}"

        channel = config.get("channel") or credential_data.get("channel") or ""
        message = config.get("message", "")

        if not message:
            raise ValueError("Slack: 'message' is required but was not set.")

        try:
            response_data = self._send_message(
                webhook_url=webhook_url,
                channel=channel,
                message=message,
            )
        except Exception as exc:
            raise ValueError(f"Slack: Failed to send message — {exc}") from exc

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

        result["slack_sent"] = True
        result["slack_response"] = response_data
        if channel:
            result["slack_channel"] = channel
        result["slack_message"] = message
        return result

    @staticmethod
    def _send_message(
        *,
        webhook_url: str,
        channel: str,
        message: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": message,
        }
        if channel:
            payload["channel"] = channel

        def _do_request() -> dict[str, Any]:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(webhook_url, json=payload)
                resp.raise_for_status()
                body_text = resp.text

            if body_text.strip() not in ("ok", ""):
                raise ValueError(f"Slack API error: {body_text}")

            return {"ok": True, "message": "Message sent successfully"}

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _do_request()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_request)
            return future.result()
