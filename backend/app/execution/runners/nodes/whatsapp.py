"""WhatsApp message runner — sends a real message via the Meta WhatsApp Cloud API.

Credential resolution
---------------------
The ``execute_workflow`` task pre-resolves every ``credential_id`` found in node
configs and stores them in:
- ``runner_context["resolved_credentials"]``       : ``str(credential_id) → api_key``
- ``runner_context["resolved_credential_data"]``   : ``str(credential_id) → token_data``

This runner reads from ``resolved_credential_data`` to get:
- ``access_token``      : Meta / WhatsApp Cloud API bearer token
- ``phone_number_id``   : The phone number ID from Meta Business Suite

Config keys
-----------
- ``credential_id``    : str — UUID of an ``app_credentials`` row (app_name="whatsapp").
- ``to_number``        : str — Recipient phone number in E.164 format (e.g. "+919876543210").
- ``template_name``    : str — Meta-approved message template name.
- ``template_params``  : list[str] — Optional parameter values for template body placeholders.
- ``language_code``    : str — Language code for the template (default: "en_US").
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppRunner:
    """Sends a template message through the Meta WhatsApp Cloud API."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}

        # ── Resolve credential data ──────────────────────────────────────────
        cred_id = config.get("credential_id")
        credential_data: dict[str, Any] = {}
        if cred_id:
            all_credential_data: dict[str, Any] = (
                context.get("resolved_credential_data") or {}
            )
            raw_data = all_credential_data.get(str(cred_id))
            if isinstance(raw_data, dict):
                credential_data = raw_data

        access_token = (
            config.get("access_token")
            or credential_data.get("access_token")
            or credential_data.get("api_key")
        )
        if not access_token and cred_id:
            resolved: dict[str, str] = context.get("resolved_credentials") or {}
            access_token = resolved.get(str(cred_id))
        if not access_token:
            raise ValueError(
                "WhatsApp: No access token available. "
                "Add a credential (app_name='whatsapp') with "
                'token_data = {"access_token": "EAAxxxx...", '
                '"phone_number_id": "...", "waba_id": "..."} '
                "and set the credential_id on the node config."
            )

        phone_number_id = (
            config.get("phone_number_id")
            or credential_data.get("phone_number_id")
        )
        if not phone_number_id:
            raise ValueError(
                "WhatsApp: 'phone_number_id' is required. "
                "Set it in the credential token_data or node config."
            )

        # ── Read message parameters ─────────────────────────────────────────
        to_number = config.get("to_number", "") or config.get("phone_number", "")
        template_name = config.get("template_name", "")
        template_params = config.get("template_params", [])
        language_code = config.get("language_code", "en_US")

        if not to_number:
            raise ValueError("WhatsApp: 'to_number' (recipient phone) is required.")
        if not template_name:
            raise ValueError("WhatsApp: 'template_name' is required.")

        # ── Call the WhatsApp Cloud API ──────────────────────────────────────
        try:
            response_data = self._send_template_message(
                access_token=access_token,
                phone_number_id=str(phone_number_id),
                to_number=str(to_number),
                template_name=template_name,
                template_params=template_params if isinstance(template_params, list) else [],
                language_code=language_code,
            )
        except Exception as exc:
            raise ValueError(f"WhatsApp: Failed to send message — {exc}") from exc

        # ── Build output ─────────────────────────────────────────────────────
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

        result["whatsapp_sent"] = True
        result["whatsapp_response"] = response_data
        result["whatsapp_to"] = to_number
        result["whatsapp_template"] = template_name
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _send_template_message(
        *,
        access_token: str,
        phone_number_id: str,
        to_number: str,
        template_name: str,
        template_params: list[str],
        language_code: str,
    ) -> dict[str, Any]:
        """POST to WhatsApp Cloud API messages endpoint (sync-safe)."""
        url = f"{WHATSAPP_API_BASE}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Build template component with parameters if provided
        template_body: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language_code},
        }
        if template_params:
            template_body["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(param)}
                        for param in template_params
                    ],
                }
            ]

        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "template",
            "template": template_body,
        }

        # DEBUG START
        print("TEMPLATE PARAMS:", template_params)
        print("FINAL PAYLOAD:", payload)
        # DEBUG END

        def _do_request() -> dict[str, Any]:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, json=payload, headers=headers)

                body = resp.json()

                # WhatsApp Cloud API returns errors in a specific shape
                if resp.status_code >= 400:
                    error_info = body.get("error", {})
                    error_msg = error_info.get("message", resp.text)
                    error_code = error_info.get("code", resp.status_code)
                    raise ValueError(
                        f"WhatsApp API error ({error_code}): {error_msg}"
                    )

                return body

        # Handle both sync and async contexts (same pattern as TelegramRunner).
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _do_request()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_request)
            return future.result()
