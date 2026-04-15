"""Google Sheets search + update runner using a service account credential."""

from __future__ import annotations

import json
import re
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


GOOGLE_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class SearchUpdateGoogleSheetsRunner:
    """Finds the first matching row and updates one column value."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        credential_data = self._resolve_credential_data(config, context)

        spreadsheet_id = str(config.get("spreadsheet_id") or "").strip()
        sheet_name = str(config.get("sheet_name") or "Sheet1").strip()
        search_column = str(config.get("search_column") or "").strip()
        search_value = str(config.get("search_value") or "").strip()
        update_column = str(config.get("update_column") or "").strip()
        update_value = config.get("update_value")

        if not spreadsheet_id:
            raise ValueError("Google Sheets Search/Update: 'spreadsheet_id' is required.")
        if not sheet_name:
            raise ValueError("Google Sheets Search/Update: 'sheet_name' is required.")
        if not search_column:
            raise ValueError("Google Sheets Search/Update: 'search_column' is required.")
        if search_value == "":
            raise ValueError("Google Sheets Search/Update: 'search_value' is required.")
        if not update_column:
            raise ValueError("Google Sheets Search/Update: 'update_column' is required.")
        if update_value is None:
            raise ValueError("Google Sheets Search/Update: 'update_value' is required.")

        service = self._build_sheets_service(credential_data)

        try:
            headers = self._fetch_header_row(service, spreadsheet_id, sheet_name)
        except Exception as exc:
            raise ValueError(
                f"Google Sheets Search/Update: Could not read sheet headers: {exc}"
            ) from exc
        search_col_index = self._resolve_column_index(search_column, headers)
        update_col_index = self._resolve_column_index(update_column, headers)

        max_col_index = max(search_col_index, update_col_index)
        data_range = f"{sheet_name}!A2:{self._index_to_column_letter(max_col_index)}"
        try:
            rows_response = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=data_range)
                .execute()
            )
        except Exception as exc:
            raise ValueError(
                f"Google Sheets Search/Update: Could not read row data: {exc}"
            ) from exc
        rows = rows_response.get("values") or []

        matched_row_number: int | None = None
        matched_row_values: list[Any] | None = None
        for row_offset, row in enumerate(rows, start=2):
            current = row[search_col_index - 1] if len(row) >= search_col_index else ""
            if str(current).strip() == search_value:
                matched_row_number = row_offset
                matched_row_values = row
                break

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)

        if matched_row_number is None:
            result.update(
                {
                    "google_sheets_updated": False,
                    "google_sheets_found": False,
                    "google_sheets_spreadsheet_id": spreadsheet_id,
                    "google_sheets_sheet_name": sheet_name,
                    "google_sheets_search_column": search_column,
                    "google_sheets_search_value": search_value,
                }
            )
            return result

        update_cell = f"{sheet_name}!{self._index_to_column_letter(update_col_index)}{matched_row_number}"
        try:
            update_response = (
                service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=update_cell,
                    valueInputOption="USER_ENTERED",
                    body={"values": [[update_value]]},
                )
                .execute()
            )
        except Exception as exc:
            raise ValueError(
                f"Google Sheets Search/Update: Failed to update matched row: {exc}"
            ) from exc

        result.update(
            {
                "google_sheets_updated": True,
                "google_sheets_found": True,
                "google_sheets_spreadsheet_id": spreadsheet_id,
                "google_sheets_sheet_name": sheet_name,
                "google_sheets_search_column": search_column,
                "google_sheets_search_value": search_value,
                "google_sheets_update_column": update_column,
                "google_sheets_update_value": update_value,
                "google_sheets_matched_row_number": matched_row_number,
                "google_sheets_matched_row_values": matched_row_values or [],
                "google_sheets_updated_range": update_response.get("updatedRange"),
                "google_sheets_updated_cells": update_response.get("updatedCells"),
            }
        )
        return result

    @staticmethod
    def _resolve_credential_data(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        cred_id = config.get("credential_id")
        if not cred_id:
            raise ValueError("Google Sheets Search/Update: 'credential_id' is required.")

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        raw_data = all_credential_data.get(str(cred_id))
        if not isinstance(raw_data, dict):
            raise ValueError(
                "Google Sheets Search/Update: Credential not found. Save a Sheets credential and select it in this node."
            )
        return raw_data

    @staticmethod
    def _build_sheets_service(credential_data: dict[str, Any]) -> Any:
        raw_service_account = (
            credential_data.get("service_account_json")
            or credential_data.get("serviceAccountJson")
        )
        if isinstance(raw_service_account, str):
            try:
                service_account_info = json.loads(raw_service_account)
            except Exception as exc:
                raise ValueError(
                    "Google Sheets Search/Update: service_account_json is not valid JSON."
                ) from exc
        elif isinstance(raw_service_account, dict):
            service_account_info = raw_service_account
        else:
            raise ValueError(
                "Google Sheets Search/Update: service_account_json is missing in selected credential."
            )

        if not isinstance(service_account_info, dict):
            raise ValueError(
                "Google Sheets Search/Update: service account payload must be a JSON object."
            )

        for required_key in ("client_email", "private_key"):
            if not str(service_account_info.get(required_key) or "").strip():
                raise ValueError(
                    f"Google Sheets Search/Update: service account payload is missing '{required_key}'."
                )

        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=[GOOGLE_SHEETS_SCOPE],
        )
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    @staticmethod
    def _fetch_header_row(service: Any, spreadsheet_id: str, sheet_name: str) -> list[str]:
        response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!1:1")
            .execute()
        )
        values = response.get("values") or []
        if not values:
            return []
        row = values[0]
        if not isinstance(row, list):
            return []
        return [str(cell or "").strip() for cell in row]

    @classmethod
    def _resolve_column_index(cls, value: str, headers: list[str]) -> int:
        token = value.strip()
        if token.isdigit():
            parsed = int(token)
            if parsed < 1:
                raise ValueError("Google Sheets Search/Update: Column index must be >= 1.")
            return parsed

        if re.fullmatch(r"[A-Za-z]+", token):
            return cls._column_letter_to_index(token)

        if headers:
            lowered = token.lower()
            for idx, header in enumerate(headers, start=1):
                if header.lower() == lowered:
                    return idx

        raise ValueError(
            f"Google Sheets Search/Update: Could not resolve column '{value}'. "
            "Use a header name, column letter (A, B, C...), or column number."
        )

    @staticmethod
    def _column_letter_to_index(column: str) -> int:
        total = 0
        for char in column.upper():
            total = (total * 26) + (ord(char) - ord("A") + 1)
        return total

    @staticmethod
    def _index_to_column_letter(index: int) -> str:
        if index < 1:
            raise ValueError("Column index must be >= 1.")
        out = []
        current = index
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            out.append(chr(ord("A") + remainder))
        return "".join(reversed(out))
