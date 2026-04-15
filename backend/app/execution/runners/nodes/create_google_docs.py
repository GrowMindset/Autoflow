"""Google Docs create runner using Google OAuth credentials."""

from __future__ import annotations

import json
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential


GOOGLE_DOCS_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


class CreateGoogleDocsRunner:
    """Creates a Google Doc and optionally writes initial content."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        credential_data = self._resolve_credential_data(config, context)
        if not is_google_oauth_credential(credential_data):
            raise ValueError(
                "Google Docs Create: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        title = str(config.get("title") or "").strip()
        if not title:
            raise ValueError("Google Docs Create: 'title' is required.")

        initial_content = str(config.get("initial_content") or "")
        docs_service = self._build_docs_service(credential_data)

        try:
            created = docs_service.documents().create(body={"title": title}).execute()
            document_id = str((created or {}).get("documentId") or "").strip()
            if not document_id:
                raise ValueError("Google Docs Create: API did not return documentId.")

            if initial_content:
                docs_service.documents().batchUpdate(
                    documentId=document_id,
                    body={
                        "requests": [
                            {
                                "insertText": {
                                    "location": {"index": 1},
                                    "text": initial_content,
                                }
                            }
                        ]
                    },
                ).execute()
        except HttpError as exc:
            google_error = self._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Docs Create: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Docs OAuth credential, ensure this account is allowed in OAuth test users, and verify Docs/Drive APIs are enabled."
                ) from exc
            raise ValueError(f"Google Docs Create: API request failed: {exc}") from exc
        except RefreshError as exc:
            raise ValueError(
                "Google Docs Create: Google credential authentication failed. "
                "Reconnect OAuth credential."
            ) from exc
        except Exception as exc:
            raise ValueError(f"Google Docs Create: API request failed: {exc}") from exc

        created_dict = created if isinstance(created, dict) else {}
        document_id = str(created_dict.get("documentId") or "")
        document_url = f"https://docs.google.com/document/d/{document_id}/edit" if document_id else ""
        created_title = str(created_dict.get("title") or "").strip() or title

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)
        result.update(
            {
                "google_docs_created": True,
                "google_docs_auth_mode": "oauth",
                "google_docs_document_id": document_id,
                "google_docs_document_url": document_url,
                "google_docs_title": created_title,
                "google_docs_initial_content_added": bool(initial_content),
            }
        )
        return result

    @staticmethod
    def _resolve_credential_data(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cred_id = config.get("credential_id")
        if not cred_id:
            raise ValueError("Google Docs Create: 'credential_id' is required.")

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        raw_data = all_credential_data.get(str(cred_id))
        if not isinstance(raw_data, dict):
            raise ValueError(
                "Google Docs Create: Credential not found. Save a Docs credential and select it in this node."
            )
        return raw_data

    @staticmethod
    def _build_docs_service(credential_data: dict[str, Any]) -> Any:
        user_credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GOOGLE_DOCS_SCOPES,
            integration_name="Google Docs Create",
        )
        return build("docs", "v1", credentials=user_credentials, cache_discovery=False)

    @staticmethod
    def _extract_google_error(exc: HttpError) -> str:
        try:
            raw = exc.content.decode("utf-8", "ignore")
            payload = json.loads(raw)
            if isinstance(payload, dict):
                err = payload.get("error")
                if isinstance(err, dict):
                    message = str(err.get("message") or "").strip()
                    status = str(err.get("status") or "").strip()
                    if message and status:
                        return f"{status}: {message}"
                    if message:
                        return message
            return raw or str(exc)
        except Exception:
            return str(exc)
