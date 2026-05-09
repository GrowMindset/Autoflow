"""Google Docs read runner using Google OAuth credentials."""

from __future__ import annotations

import json
import re
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential


GOOGLE_DOCS_READ_SCOPES = [
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


class ReadGoogleDocsRunner:
    """Reads a Google Doc and returns extracted plain text."""

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
                "Google Docs Read: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        document_id = self._resolve_document_id(config)
        include_raw_json = self._coerce_bool(config.get("include_raw_json"), default=False)
        max_characters = self._parse_max_characters(config.get("max_characters"))

        docs_service = self._build_docs_service(credential_data)
        document = self._safe_google_call(
            "Could not read document",
            lambda: docs_service.documents()
            .get(
                documentId=document_id,
                fields="documentId,title,revisionId,body/content",
            )
            .execute(),
        )

        title = str((document or {}).get("title") or "").strip()
        revision_id = str((document or {}).get("revisionId") or "").strip()
        extracted_text = self._extract_plain_text(document)
        full_length = len(extracted_text)
        truncated = False
        if max_characters is not None and full_length > max_characters:
            extracted_text = extracted_text[:max_characters]
            truncated = True

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)

        result.update(
            {
                "google_docs_read": True,
                "google_docs_auth_mode": "oauth",
                "google_docs_document_id": document_id,
                "google_docs_document_url": f"https://docs.google.com/document/d/{document_id}/edit",
                "google_docs_title": title,
                "google_docs_revision_id": revision_id,
                "google_docs_text": extracted_text,
                "google_docs_text_length": len(extracted_text),
                "google_docs_text_full_length": full_length,
                "google_docs_text_truncated": truncated,
            }
        )
        if include_raw_json:
            result["google_docs_document"] = document

        return result

    @staticmethod
    def _resolve_credential_data(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cred_id = config.get("credential_id")
        if not cred_id:
            raise ValueError("Google Docs Read: 'credential_id' is required.")

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        raw_data = all_credential_data.get(str(cred_id))
        if not isinstance(raw_data, dict):
            raise ValueError(
                "Google Docs Read: Credential not found. Save a Docs credential and select it in this node."
            )
        return raw_data

    @staticmethod
    def _build_docs_service(credential_data: dict[str, Any]) -> Any:
        user_credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GOOGLE_DOCS_READ_SCOPES,
            integration_name="Google Docs Read",
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

    @classmethod
    def _safe_google_call(cls, action: str, fn):
        try:
            return fn()
        except RefreshError as exc:
            raise ValueError(
                "Google Docs Read: Google credential authentication failed. Reconnect OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = cls._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Docs Read: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Docs OAuth credential, ensure this account is allowed in OAuth test users, and verify Docs/Drive APIs are enabled."
                ) from exc
            raise ValueError(f"Google Docs Read: {action}: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"Google Docs Read: {action}: {exc}") from exc

    @classmethod
    def _resolve_document_id(cls, config: dict[str, Any]) -> str:
        source_type = str(config.get("document_source_type") or "id").strip().lower()
        document_id = str(config.get("document_id") or "").strip()
        document_url = str(config.get("document_url") or "").strip()

        if source_type not in {"id", "url"}:
            raise ValueError("Google Docs Read: 'document_source_type' must be 'id' or 'url'.")

        if source_type == "url":
            if not document_url:
                raise ValueError(
                    "Google Docs Read: 'document_url' is required when source type is url."
                )
            parsed = cls._extract_document_id_from_url(document_url)
            if not parsed:
                raise ValueError("Google Docs Read: Could not parse document ID from document_url.")
            return parsed

        if document_id:
            return document_id

        if document_url:
            parsed = cls._extract_document_id_from_url(document_url)
            if parsed:
                return parsed

        raise ValueError("Google Docs Read: 'document_id' is required.")

    @staticmethod
    def _extract_document_id_from_url(document_url: str) -> str:
        token = str(document_url or "").strip()
        if not token:
            return ""

        match = re.search(r"/document/d/([a-zA-Z0-9-_]+)", token)
        if match:
            return str(match.group(1) or "").strip()

        match = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", token)
        if match:
            return str(match.group(1) or "").strip()

        if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", token):
            return token

        return ""

    @classmethod
    def _extract_plain_text(cls, document_payload: dict[str, Any]) -> str:
        body = (document_payload or {}).get("body") or {}
        content = body.get("content") or []
        chunks = cls._collect_structural_text(content)
        return "".join(chunks)

    @classmethod
    def _collect_structural_text(cls, structural_elements: Any) -> list[str]:
        if not isinstance(structural_elements, list):
            return []

        chunks: list[str] = []
        for element in structural_elements:
            if not isinstance(element, dict):
                continue

            paragraph = element.get("paragraph")
            if isinstance(paragraph, dict):
                para_elements = paragraph.get("elements") or []
                for para_element in para_elements:
                    if not isinstance(para_element, dict):
                        continue
                    text_run = para_element.get("textRun")
                    if isinstance(text_run, dict):
                        content = text_run.get("content")
                        if content is not None:
                            chunks.append(str(content))

            table = element.get("table")
            if isinstance(table, dict):
                rows = table.get("tableRows") or []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    cells = row.get("tableCells") or []
                    for cell in cells:
                        if not isinstance(cell, dict):
                            continue
                        chunks.extend(cls._collect_structural_text(cell.get("content")))

            toc = element.get("tableOfContents")
            if isinstance(toc, dict):
                chunks.extend(cls._collect_structural_text(toc.get("content")))

        return chunks

    @staticmethod
    def _coerce_bool(raw_value: Any, *, default: bool) -> bool:
        if raw_value is None:
            return default
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, (int, float)):
            return raw_value != 0
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _parse_max_characters(raw_value: Any) -> int | None:
        if raw_value in (None, ""):
            return None
        try:
            parsed = int(str(raw_value).strip())
        except Exception as exc:
            raise ValueError("Google Docs Read: 'max_characters' must be an integer.") from exc
        if parsed <= 0:
            raise ValueError("Google Docs Read: 'max_characters' must be > 0.")
        return parsed
