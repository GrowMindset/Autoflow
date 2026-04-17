"""Google Sheets create runner using Google OAuth credentials."""

from __future__ import annotations

import json
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential


GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class CreateGoogleSheetsRunner:
    """Creates a new spreadsheet in Google Sheets."""

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
                "Google Sheets Create: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        title = str(config.get("title") or "").strip()
        if not title:
            raise ValueError("Google Sheets Create: 'title' is required.")

        sheet_name = str(config.get("sheet_name") or "").strip()
        columns = self._collect_columns(config.get("columns"))

        service = self._build_sheets_service(credential_data)
        body: dict[str, Any] = {"properties": {"title": title}}
        if sheet_name:
            body["sheets"] = [{"properties": {"title": sheet_name}}]

        try:
            created = (
                service.spreadsheets()
                .create(
                    body=body,
                    fields="spreadsheetId,spreadsheetUrl,properties.title,sheets.properties.title",
                )
                .execute()
            )
        except HttpError as exc:
            google_error = self._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Sheets Create: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Sheets OAuth credential, ensure this account is allowed in OAuth test users, and verify Sheets/Drive APIs are enabled."
                ) from exc
            raise ValueError(f"Google Sheets Create: API request failed: {exc}") from exc
        except RefreshError as exc:
            raise ValueError(
                "Google Sheets Create: Google credential authentication failed. "
                "Reconnect OAuth credential."
            ) from exc
        except Exception as exc:
            raise ValueError(f"Google Sheets Create: API request failed: {exc}") from exc

        created_dict = created if isinstance(created, dict) else {}
        created_title = (created_dict.get("properties") or {}).get("title")
        created_sheets = created_dict.get("sheets") or []
        sheet_titles = []
        if isinstance(created_sheets, list):
            for item in created_sheets:
                title_value = ((item or {}).get("properties") or {}).get("title")
                if isinstance(title_value, str) and title_value.strip():
                    sheet_titles.append(title_value)

        if columns:
            target_sheet_name = sheet_name or (sheet_titles[0] if sheet_titles else "Sheet1")
            try:
                self._write_header_row(
                    service=service,
                    spreadsheet_id=str(created_dict.get("spreadsheetId") or ""),
                    sheet_name=target_sheet_name,
                    headers=columns,
                )
            except RefreshError as exc:
                raise ValueError(
                    "Google Sheets Create: Google credential authentication failed while writing column headers. "
                    "Reconnect OAuth credential."
                ) from exc
            except HttpError as exc:
                google_error = self._extract_google_error(exc)
                if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                    raise ValueError(
                        "Google Sheets Create: Permission denied (403) while writing column headers. "
                        f"Google said: {google_error}. "
                        "Reconnect Sheets OAuth credential, ensure this account is allowed in OAuth test users, and verify Sheets/Drive APIs are enabled."
                    ) from exc
                raise ValueError(
                    f"Google Sheets Create: Failed to write column headers: {exc}"
                ) from exc
            except Exception as exc:
                raise ValueError(
                    f"Google Sheets Create: Failed to write column headers: {exc}"
                ) from exc

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)
        result.update(
            {
                "google_sheets_created": True,
                "google_sheets_auth_mode": "oauth",
                "google_sheets_spreadsheet_id": created_dict.get("spreadsheetId"),
                "google_sheets_spreadsheet_url": created_dict.get("spreadsheetUrl"),
                "google_sheets_title": created_title or title,
                "google_sheets_sheet_names": sheet_titles,
                "google_sheets_headers": columns,
            }
        )
        return result

    @staticmethod
    def _resolve_credential_data(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cred_id = config.get("credential_id")
        if not cred_id:
            raise ValueError("Google Sheets Create: 'credential_id' is required.")

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        raw_data = all_credential_data.get(str(cred_id))
        if not isinstance(raw_data, dict):
            raise ValueError(
                "Google Sheets Create: Credential not found. Save a Sheets credential and select it in this node."
            )
        return raw_data

    @staticmethod
    def _build_sheets_service(credential_data: dict[str, Any]) -> Any:
        user_credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GOOGLE_SHEETS_SCOPES,
            integration_name="Google Sheets Create",
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

    @staticmethod
    def _collect_columns(raw_columns: Any) -> list[str]:
        if not isinstance(raw_columns, list):
            return []

        seen_lower: set[str] = set()
        columns: list[str] = []
        for item in raw_columns:
            token = str(item or "").strip()
            if not token:
                continue
            lowered = token.lower()
            if lowered in seen_lower:
                continue
            seen_lower.add(lowered)
            columns.append(token)
        return columns

    @classmethod
    def _write_header_row(
        cls,
        *,
        service: Any,
        spreadsheet_id: str,
        sheet_name: str,
        headers: list[str],
    ) -> None:
        if not spreadsheet_id or not headers:
            return
        end_col = cls._index_to_column_letter(len(headers))
        target_range = f"{sheet_name}!A1:{end_col}1"
        (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=target_range,
                valueInputOption="USER_ENTERED",
                body={"values": [headers]},
            )
            .execute()
        )

    @staticmethod
    def _index_to_column_letter(index: int) -> str:
        if index < 1:
            raise ValueError("Column index must be >= 1.")
        out: list[str] = []
        current = index
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            out.append(chr(ord("A") + remainder))
        return "".join(reversed(out))
