"""Gmail label application runner using Google OAuth credentials."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .gmail_common import GMAIL_MODIFY_SCOPES, extract_google_error, resolve_gmail_credential_data
from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential


class AddGmailLabelRunner:
    """Finds or creates a Gmail label, then applies it to a message."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        credential_data = resolve_gmail_credential_data(config, context, integration_name="Gmail Label")

        message_id = str(config.get("message_id") or "").strip()
        label_name = str(config.get("label_name") or "").strip()
        if not message_id:
            raise ValueError("Gmail Label: 'message_id' is required.")
        if not label_name:
            raise ValueError("Gmail Label: 'label_name' is required.")

        if not is_google_oauth_credential(credential_data):
            raise ValueError(
                "Gmail Label: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        label_id = self._apply_label_via_gmail_api(
            credential_data=credential_data,
            message_id=message_id,
            label_name=label_name,
        )

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)
        result.update(
            {
                "message_id": message_id,
                "label_id": label_id,
                "label_name": label_name,
                "applied_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
        return result

    def _apply_label_via_gmail_api(
        self,
        *,
        credential_data: dict[str, Any],
        message_id: str,
        label_name: str,
    ) -> str:
        credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GMAIL_MODIFY_SCOPES,
            integration_name="Gmail Label",
        )
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        try:
            label_id = self._find_or_create_label_id(service=service, label_name=label_name)
            (
                service.users()
                .messages()
                .modify(
                    userId="me",
                    id=message_id,
                    body={"addLabelIds": [label_id]},
                )
                .execute()
            )
            return label_id
        except RefreshError as exc:
            raise ValueError(
                "Gmail Label: OAuth token refresh failed. Reconnect Google OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = extract_google_error(exc)
            lowered = google_error.lower()
            if "not found" in lowered or "invalid id" in lowered:
                raise ValueError(
                    "Gmail Label: invalid message_id. Use a Gmail API message id from an upstream Gmail node."
                ) from exc
            raise ValueError(f"Gmail Label: Gmail API label update failed: {google_error}") from exc

    def _find_or_create_label_id(self, *, service: Any, label_name: str) -> str:
        labels_response = service.users().labels().list(userId="me").execute()
        labels = labels_response.get("labels", []) if isinstance(labels_response, dict) else []
        for label in labels:
            if not isinstance(label, dict):
                continue
            if str(label.get("name") or "") == label_name:
                label_id = str(label.get("id") or "").strip()
                if label_id:
                    return label_id

        create_response = (
            service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": label_name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        label_id = str(create_response.get("id") or "").strip() if isinstance(create_response, dict) else ""
        if not label_id:
            raise ValueError("Gmail Label: Gmail API did not return a label id.")
        return label_id
