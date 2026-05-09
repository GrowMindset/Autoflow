"""Google Sheets read runner using Google OAuth credentials."""

from __future__ import annotations

import json
import re
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential


GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


class ReadGoogleSheetsRunner:
    """Reads rows from a Google Sheets worksheet."""

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
                "Google Sheets Read: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        spreadsheet_id = self._resolve_spreadsheet_id(config)
        sheet_name = str(config.get("sheet_name") or "Sheet1").strip()
        if not sheet_name:
            raise ValueError("Google Sheets Read: 'sheet_name' is required.")

        source_range = str(config.get("range") or "").strip()
        first_row_as_header = self._coerce_bool(config.get("first_row_as_header"), default=True)
        include_empty_rows = self._coerce_bool(config.get("include_empty_rows"), default=False)
        max_rows = self._parse_max_rows(config.get("max_rows"))

        service = self._build_sheets_service(credential_data)
        sheet_name = self._safe_google_call(
            "Could not resolve sheet name",
            lambda: self._resolve_sheet_name(service, spreadsheet_id, sheet_name),
        )

        target_range = self._build_target_range(sheet_name=sheet_name, source_range=source_range)
        values_response = self._safe_google_call(
            "Could not read sheet values",
            lambda: service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=target_range)
            .execute(),
        )
        rows = values_response.get("values") or []
        if not isinstance(rows, list):
            rows = []

        if not include_empty_rows:
            rows = [row for row in rows if self._row_has_value(row)]

        if max_rows is not None:
            rows = rows[:max_rows]

        headers: list[str] = []
        parsed_rows: list[Any]
        if first_row_as_header:
            if rows:
                headers = self._normalize_headers(rows[0] if isinstance(rows[0], list) else [])
                data_rows = rows[1:]
                parsed_rows = [self._map_row_to_object(headers, row) for row in data_rows]
            else:
                parsed_rows = []
        else:
            parsed_rows = rows

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)

        result.update(
            {
                "google_sheets_auth_mode": "oauth",
                "google_sheets_spreadsheet_id": spreadsheet_id,
                "google_sheets_sheet_name": sheet_name,
                "google_sheets_range": target_range,
                "google_sheets_row_count": len(parsed_rows),
                "google_sheets_data": parsed_rows,
                "google_sheets_first_row_as_header": first_row_as_header,
            }
        )
        if first_row_as_header:
            result["google_sheets_headers"] = headers

        return result

    @staticmethod
    def _resolve_credential_data(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cred_id = config.get("credential_id")
        if not cred_id:
            raise ValueError("Google Sheets Read: 'credential_id' is required.")

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        raw_data = all_credential_data.get(str(cred_id))
        if not isinstance(raw_data, dict):
            raise ValueError(
                "Google Sheets Read: Credential not found. Save a Sheets credential and select it in this node."
            )
        return raw_data

    @staticmethod
    def _build_sheets_service(credential_data: dict[str, Any]) -> Any:
        user_credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GOOGLE_SHEETS_SCOPES,
            integration_name="Google Sheets Read",
        )
        return build("sheets", "v4", credentials=user_credentials, cache_discovery=False)

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
                "Google Sheets Read: Google credential authentication failed. Reconnect OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = cls._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Sheets Read: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Sheets OAuth credential, ensure this account is allowed in OAuth test users, and verify Sheets/Drive APIs are enabled."
                ) from exc
            raise ValueError(f"Google Sheets Read: {action}: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"Google Sheets Read: {action}: {exc}") from exc

    @staticmethod
    def _build_target_range(*, sheet_name: str, source_range: str) -> str:
        if not source_range:
            return f"{sheet_name}!A:ZZ"
        if "!" in source_range:
            return source_range
        return f"{sheet_name}!{source_range}"

    @staticmethod
    def _row_has_value(raw_row: Any) -> bool:
        if not isinstance(raw_row, list):
            return bool(raw_row)
        return any(str(cell or "").strip() for cell in raw_row)

    @staticmethod
    def _normalize_headers(raw_header_row: list[Any]) -> list[str]:
        normalized: list[str] = []
        seen: dict[str, int] = {}
        for index, raw_value in enumerate(raw_header_row, start=1):
            token = str(raw_value or "").strip() or f"column_{index}"
            base = token
            next_count = seen.get(base, 0) + 1
            seen[base] = next_count
            if next_count > 1:
                token = f"{base}_{next_count}"
            normalized.append(token)
        return normalized

    @staticmethod
    def _map_row_to_object(headers: list[str], raw_row: Any) -> dict[str, Any]:
        row = raw_row if isinstance(raw_row, list) else []
        mapped: dict[str, Any] = {}
        for index, header in enumerate(headers):
            mapped[header] = row[index] if index < len(row) else ""
        if len(row) > len(headers):
            for index in range(len(headers), len(row)):
                mapped[f"column_{index + 1}"] = row[index]
        return mapped

    @classmethod
    def _resolve_spreadsheet_id(cls, config: dict[str, Any]) -> str:
        source_type = str(config.get("spreadsheet_source_type") or "id").strip().lower()
        spreadsheet_id = str(config.get("spreadsheet_id") or "").strip()
        spreadsheet_url = str(config.get("spreadsheet_url") or "").strip()

        if source_type == "url":
            if not spreadsheet_url:
                raise ValueError(
                    "Google Sheets Read: 'spreadsheet_url' is required when source type is url."
                )
            parsed = cls._extract_spreadsheet_id_from_url(spreadsheet_url)
            if not parsed:
                raise ValueError(
                    "Google Sheets Read: Could not parse spreadsheet ID from spreadsheet_url."
                )
            return parsed

        if spreadsheet_id:
            return spreadsheet_id

        if spreadsheet_url:
            parsed = cls._extract_spreadsheet_id_from_url(spreadsheet_url)
            if parsed:
                return parsed

        raise ValueError("Google Sheets Read: 'spreadsheet_id' is required.")

    @staticmethod
    def _extract_spreadsheet_id_from_url(spreadsheet_url: str) -> str:
        token = str(spreadsheet_url or "").strip()
        if not token:
            return ""

        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", token)
        if match:
            return str(match.group(1) or "").strip()

        match = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", token)
        if match:
            return str(match.group(1) or "").strip()

        if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", token):
            return token

        return ""

    @staticmethod
    def _resolve_sheet_name(service: Any, spreadsheet_id: str, sheet_name: str) -> str:
        requested = str(sheet_name or "").strip()
        if not requested:
            raise ValueError("Google Sheets Read: 'sheet_name' is required.")

        response = (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(title))")
            .execute()
        )
        titles = [
            str((sheet.get("properties") or {}).get("title") or "").strip()
            for sheet in (response.get("sheets") or [])
        ]
        titles = [title for title in titles if title]
        if not titles:
            raise ValueError("Google Sheets Read: No sheets found in spreadsheet metadata.")

        if requested in titles:
            return requested

        lowered = requested.lower()
        for title in titles:
            if title.lower() == lowered:
                return title

        available = ", ".join(titles[:10])
        if len(titles) > 10:
            available = f"{available}, ..."
        raise ValueError(
            f"Google Sheets Read: Sheet '{requested}' was not found. Available sheets: {available}"
        )

    @staticmethod
    def _coerce_bool(raw_value: Any, *, default: bool) -> bool:
        if raw_value is None:
            return default
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, (int, float)):
            return bool(raw_value)
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _parse_max_rows(raw_value: Any) -> int | None:
        if raw_value in (None, ""):
            return None
        try:
            parsed = int(str(raw_value).strip())
        except Exception as exc:
            raise ValueError("Google Sheets Read: max_rows must be an integer.") from exc
        if parsed <= 0:
            raise ValueError("Google Sheets Read: max_rows must be > 0.")
        return parsed
