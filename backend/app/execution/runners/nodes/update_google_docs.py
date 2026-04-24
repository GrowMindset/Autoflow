"""Google Docs update runner using Google OAuth credentials."""

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


class UpdateGoogleDocsRunner:
    """Updates Google Docs content with append/replace operations."""

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
                "Google Docs Update: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        document_id = str(config.get("document_id") or "").strip()
        operation = str(config.get("operation") or "append_text").strip().lower()
        text = str(config.get("text") or "")
        image = str(config.get("image") or "").strip()
        match_text = str(config.get("match_text") or "")
        match_case = bool(config.get("match_case", False))

        if not document_id:
            raise ValueError("Google Docs Update: 'document_id' is required.")
        if operation not in {"append_text", "replace_all_text"}:
            raise ValueError("Google Docs Update: 'operation' must be append_text or replace_all_text.")
        if not text and not image:
            raise ValueError("Google Docs Update: provide either 'text' or 'image'.")
        if operation == "replace_all_text" and not match_text:
            raise ValueError("Google Docs Update: 'match_text' is required for replace_all_text operation.")

        docs_service = self._build_docs_service(credential_data)

        try:
            document = docs_service.documents().get(
                documentId=document_id,
                fields="documentId,title,body/content/endIndex",
            ).execute()

            requests: list[dict[str, Any]]
            response_meta: dict[str, Any] = {}
            if operation == "append_text":
                end_index = self._resolve_end_index(document)
                requests = []
                if text:
                    requests.append({
                        "insertText": {
                            "location": {"index": end_index},
                            "text": text,
                        }
                    })
                if image:
                    requests.append({
                        "insertInlineImage": {
                            "location": {"index": end_index + len(text)},
                            "uri": image,
                        }
                    })
                response_meta["google_docs_inserted_chars"] = len(text)
                response_meta["google_docs_inserted_image"] = bool(image)
            else:
                requests = [
                    {
                        "replaceAllText": {
                            "containsText": {
                                "text": match_text,
                                "matchCase": match_case,
                            },
                            "replaceText": text,
                        }
                    }
                ]

            update_response = docs_service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": requests},
            ).execute()

            if operation == "replace_all_text":
                occurrences = 0
                for item in update_response.get("replies", []) or []:
                    if isinstance(item, dict) and isinstance(item.get("replaceAllText"), dict):
                        occurrences = int(item["replaceAllText"].get("occurrencesChanged") or 0)
                        break
                response_meta["google_docs_replaced_occurrences"] = occurrences
                if image:
                    end_index = self._resolve_end_index(document)
                    docs_service.documents().batchUpdate(
                        documentId=document_id,
                        body={
                            "requests": [
                                {
                                    "insertInlineImage": {
                                        "location": {"index": end_index},
                                        "uri": image,
                                    }
                                }
                            ]
                        },
                    ).execute()
                    response_meta["google_docs_inserted_image"] = True
        except HttpError as exc:
            google_error = self._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Docs Update: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Docs OAuth credential, ensure this account is allowed in OAuth test users, and verify Docs/Drive APIs are enabled."
                ) from exc
            raise ValueError(f"Google Docs Update: API request failed: {exc}") from exc
        except RefreshError as exc:
            raise ValueError(
                "Google Docs Update: Google credential authentication failed. "
                "Reconnect OAuth credential."
            ) from exc
        except Exception as exc:
            raise ValueError(f"Google Docs Update: API request failed: {exc}") from exc

        title = str((document or {}).get("title") or "").strip()
        document_url = f"https://docs.google.com/document/d/{document_id}/edit"

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)
        result.update(
            {
                "google_docs_updated": True,
                "google_docs_auth_mode": "oauth",
                "google_docs_document_id": document_id,
                "google_docs_document_url": document_url,
                "google_docs_title": title,
                "google_docs_operation": operation,
                "google_docs_text": text,
                "google_docs_inserted_image": bool(image),
                **response_meta,
            }
        )
        return result

    @staticmethod
    def _resolve_end_index(document_payload: dict[str, Any]) -> int:
        content = ((document_payload or {}).get("body") or {}).get("content") or []
        max_end_index = 1
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                end_index = item.get("endIndex")
                if isinstance(end_index, int) and end_index > max_end_index:
                    max_end_index = end_index
        return max(1, max_end_index - 1)

    @staticmethod
    def _resolve_credential_data(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cred_id = config.get("credential_id")
        if not cred_id:
            raise ValueError("Google Docs Update: 'credential_id' is required.")

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        raw_data = all_credential_data.get(str(cred_id))
        if not isinstance(raw_data, dict):
            raise ValueError(
                "Google Docs Update: Credential not found. Save a Docs credential and select it in this node."
            )
        return raw_data

    @staticmethod
    def _build_docs_service(credential_data: dict[str, Any]) -> Any:
        user_credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GOOGLE_DOCS_SCOPES,
            integration_name="Google Docs Update",
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
