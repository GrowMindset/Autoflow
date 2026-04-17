"""Google Sheets search + update runner using Google OAuth credentials."""

from __future__ import annotations

import json
import re
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .google_oauth_utils import build_google_user_credentials, is_google_oauth_credential


GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SearchUpdateGoogleSheetsRunner:
    """Finds the first matching row and updates one or more column values."""

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
                "Google Sheets Search/Update: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        spreadsheet_id = str(config.get("spreadsheet_id") or "").strip()
        sheet_name = str(config.get("sheet_name") or "Sheet1").strip()
        search_column = str(config.get("search_column") or "").strip()
        search_value = str(config.get("search_value") or "").strip()
        update_pairs = self._collect_update_pairs(config)
        auto_create_headers = self._coerce_bool(config.get("auto_create_headers"), default=True)
        upsert_if_not_found = self._coerce_bool(config.get("upsert_if_not_found"), default=False)

        if not spreadsheet_id:
            raise ValueError("Google Sheets Search/Update: 'spreadsheet_id' is required.")
        if not sheet_name:
            raise ValueError("Google Sheets Search/Update: 'sheet_name' is required.")
        if not search_column:
            raise ValueError("Google Sheets Search/Update: 'search_column' is required.")
        if search_value == "":
            raise ValueError("Google Sheets Search/Update: 'search_value' is required.")
        if not update_pairs:
            raise ValueError(
                "Google Sheets Search/Update: Provide at least one update mapping (update_mappings) "
                "or legacy update_column/update_value."
            )

        service = self._build_sheets_service(credential_data)

        try:
            headers = self._fetch_header_row(service, spreadsheet_id, sheet_name)
        except RefreshError as exc:
            raise ValueError(
                "Google Sheets Search/Update: Google credential authentication failed. "
                "Reconnect OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = self._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Sheets Search/Update: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Sheets OAuth credential, ensure this account is allowed in OAuth test users, and verify Sheets/Drive APIs are enabled."
                ) from exc
            raise ValueError(
                f"Google Sheets Search/Update: Could not read sheet headers: {exc}"
            ) from exc
        except Exception as exc:
            raise ValueError(
                f"Google Sheets Search/Update: Could not read sheet headers: {exc}"
            ) from exc

        update_columns = [pair["column"] for pair in update_pairs]
        try:
            headers = self._ensure_headers(
                service=service,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                headers=headers,
                search_column=search_column,
                update_columns=update_columns,
                input_data=input_data,
                auto_create_headers=auto_create_headers,
            )
        except RefreshError as exc:
            raise ValueError(
                "Google Sheets Search/Update: Google credential authentication failed. "
                "Reconnect OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = self._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Sheets Search/Update: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Sheets OAuth credential, ensure this account is allowed in OAuth test users, and verify Sheets/Drive APIs are enabled."
                ) from exc
            raise ValueError(
                f"Google Sheets Search/Update: Could not initialize sheet headers: {exc}"
            ) from exc
        except Exception as exc:
            raise ValueError(
                f"Google Sheets Search/Update: Could not initialize sheet headers: {exc}"
            ) from exc

        search_col_index = self._resolve_column_index(search_column, headers)
        resolved_updates_by_index: dict[int, dict[str, Any]] = {}
        for pair in update_pairs:
            col_index = self._resolve_column_index(pair["column"], headers)
            resolved_updates_by_index[col_index] = {
                "column": pair["column"],
                "index": col_index,
                "value": pair.get("value"),
            }
        resolved_updates = sorted(
            resolved_updates_by_index.values(),
            key=lambda item: int(item["index"]),
        )
        if not resolved_updates:
            raise ValueError(
                "Google Sheets Search/Update: Could not resolve any update column from update mappings."
            )

        max_update_col_index = max(int(item["index"]) for item in resolved_updates)
        max_col_index = max(search_col_index, max_update_col_index)

        data_range = f"{sheet_name}!A2:{self._index_to_column_letter(max_col_index)}"
        try:
            rows_response = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=data_range)
                .execute()
            )
        except RefreshError as exc:
            raise ValueError(
                "Google Sheets Search/Update: Google credential authentication failed. "
                "Reconnect OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = self._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Sheets Search/Update: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Sheets OAuth credential, ensure this account is allowed in OAuth test users, and verify Sheets/Drive APIs are enabled."
                ) from exc
            raise ValueError(
                f"Google Sheets Search/Update: Could not read row data: {exc}"
            ) from exc
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

        mappings_meta = [
            {
                "column": item["column"],
                "column_index": item["index"],
                "value": item.get("value"),
            }
            for item in resolved_updates
        ]
        primary_update = resolved_updates[0]

        if matched_row_number is None:
            if upsert_if_not_found:
                row_width = max_col_index
                new_row = [""] * row_width
                new_row[search_col_index - 1] = search_value
                for item in resolved_updates:
                    new_row[int(item["index"]) - 1] = item.get("value")

                append_range = f"{sheet_name}!A2:{self._index_to_column_letter(row_width)}"
                try:
                    append_response = (
                        service.spreadsheets()
                        .values()
                        .append(
                            spreadsheetId=spreadsheet_id,
                            range=append_range,
                            valueInputOption="USER_ENTERED",
                            insertDataOption="INSERT_ROWS",
                            body={"values": [new_row]},
                        )
                        .execute()
                    )
                except RefreshError as exc:
                    raise ValueError(
                        "Google Sheets Search/Update: Google credential authentication failed. "
                        "Reconnect OAuth credential."
                    ) from exc
                except HttpError as exc:
                    google_error = self._extract_google_error(exc)
                    if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                        raise ValueError(
                            "Google Sheets Search/Update: Permission denied (403) while using Google OAuth. "
                            f"Google said: {google_error}. "
                            "Reconnect Sheets OAuth credential, ensure this account is allowed in OAuth test users, and verify Sheets/Drive APIs are enabled."
                        ) from exc
                    raise ValueError(
                        f"Google Sheets Search/Update: Failed to append row for missing match: {exc}"
                    ) from exc
                except Exception as exc:
                    raise ValueError(
                        f"Google Sheets Search/Update: Failed to append row for missing match: {exc}"
                    ) from exc

                append_updates = append_response.get("updates") if isinstance(append_response, dict) else {}
                result.update(
                    {
                        "google_sheets_updated": True,
                        "google_sheets_found": False,
                        "google_sheets_upserted": True,
                        "google_sheets_auth_mode": "oauth",
                        "google_sheets_spreadsheet_id": spreadsheet_id,
                        "google_sheets_sheet_name": sheet_name,
                        "google_sheets_search_column": search_column,
                        "google_sheets_search_value": search_value,
                        "google_sheets_update_column": primary_update["column"],
                        "google_sheets_update_value": primary_update.get("value"),
                        "google_sheets_update_mappings": mappings_meta,
                        "google_sheets_updated_range": (
                            append_updates.get("updatedRange")
                            if isinstance(append_updates, dict)
                            else None
                        ),
                        "google_sheets_updated_cells": (
                            append_updates.get("updatedCells")
                            if isinstance(append_updates, dict)
                            else None
                        ),
                    }
                )
                return result

            result.update(
                {
                    "google_sheets_updated": False,
                    "google_sheets_found": False,
                    "google_sheets_upserted": False,
                    "google_sheets_auth_mode": "oauth",
                    "google_sheets_spreadsheet_id": spreadsheet_id,
                    "google_sheets_sheet_name": sheet_name,
                    "google_sheets_search_column": search_column,
                    "google_sheets_search_value": search_value,
                    "google_sheets_update_mappings": mappings_meta,
                }
            )
            return result

        row_width = max_col_index
        merged_row = list(matched_row_values or [])
        if len(merged_row) < row_width:
            merged_row.extend([""] * (row_width - len(merged_row)))
        for item in resolved_updates:
            merged_row[int(item["index"]) - 1] = item.get("value")

        update_range = (
            f"{sheet_name}!A{matched_row_number}:"
            f"{self._index_to_column_letter(row_width)}{matched_row_number}"
        )
        try:
            update_response = (
                service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=update_range,
                    valueInputOption="USER_ENTERED",
                    body={"values": [merged_row[:row_width]]},
                )
                .execute()
            )
        except RefreshError as exc:
            raise ValueError(
                "Google Sheets Search/Update: Google credential authentication failed. "
                "Reconnect OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = self._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Sheets Search/Update: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Sheets OAuth credential, ensure this account is allowed in OAuth test users, and verify Sheets/Drive APIs are enabled."
                ) from exc
            raise ValueError(
                f"Google Sheets Search/Update: Failed to update matched row: {exc}"
            ) from exc
        except Exception as exc:
            raise ValueError(
                f"Google Sheets Search/Update: Failed to update matched row: {exc}"
            ) from exc

        result.update(
            {
                "google_sheets_updated": True,
                "google_sheets_found": True,
                "google_sheets_auth_mode": "oauth",
                "google_sheets_spreadsheet_id": spreadsheet_id,
                "google_sheets_sheet_name": sheet_name,
                "google_sheets_search_column": search_column,
                "google_sheets_search_value": search_value,
                "google_sheets_update_column": primary_update["column"],
                "google_sheets_update_value": primary_update.get("value"),
                "google_sheets_update_mappings": mappings_meta,
                "google_sheets_upserted": False,
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
        user_credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GOOGLE_SHEETS_SCOPES,
            integration_name="Google Sheets Search/Update",
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
            if normalized in {"0", "false", "no", "off", ""}:
                return False
        return bool(raw_value)

    @staticmethod
    def _collect_update_pairs(config: dict[str, Any]) -> list[dict[str, Any]]:
        pairs: list[dict[str, Any]] = []

        raw_mappings = config.get("update_mappings")
        if isinstance(raw_mappings, list):
            for raw_item in raw_mappings:
                if not isinstance(raw_item, dict):
                    continue
                column = str(
                    raw_item.get("column")
                    or raw_item.get("update_column")
                    or raw_item.get("name")
                    or ""
                ).strip()
                if not column:
                    continue
                value = raw_item.get("value")
                if "value" not in raw_item and "update_value" in raw_item:
                    value = raw_item.get("update_value")
                pairs.append({"column": column, "value": value})

        if pairs:
            return pairs

        legacy_column = str(config.get("update_column") or "").strip()
        if legacy_column and "update_value" in config:
            return [{"column": legacy_column, "value": config.get("update_value")}]

        return []

    @classmethod
    def _ensure_headers(
        cls,
        *,
        service: Any,
        spreadsheet_id: str,
        sheet_name: str,
        headers: list[str],
        search_column: str,
        update_columns: list[str],
        input_data: Any,
        auto_create_headers: bool,
    ) -> list[str]:
        # Preserve positional indices (including intentional blanks) so
        # header-name resolution always maps to the actual sheet column.
        normalized_headers = [str(item or "").strip() for item in headers]
        while normalized_headers and normalized_headers[-1] == "":
            normalized_headers.pop()
        if not auto_create_headers:
            return normalized_headers

        desired_headers: list[str] = []

        def _add_header(value: str) -> None:
            token = str(value or "").strip()
            if not token:
                return
            if token.lower() not in {item.lower() for item in desired_headers}:
                desired_headers.append(token)

        if not cls._is_column_reference(search_column):
            _add_header(search_column)

        for update_column in update_columns:
            if not cls._is_column_reference(update_column):
                _add_header(update_column)

        if not normalized_headers and isinstance(input_data, dict):
            for key in input_data.keys():
                key_token = str(key or "").strip()
                if key_token and key_token not in {"triggered", "trigger_type"}:
                    _add_header(key_token)

        if not desired_headers and normalized_headers:
            return normalized_headers

        merged_headers = list(normalized_headers)
        existing_lower = {item.lower() for item in merged_headers if item}
        for header in desired_headers:
            if header.lower() not in existing_lower:
                merged_headers.append(header)
                existing_lower.add(header.lower())

        if not merged_headers or merged_headers == normalized_headers:
            return normalized_headers

        cls._write_header_row(
            service=service,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            headers=merged_headers,
        )
        return merged_headers

    @classmethod
    def _resolve_column_index(cls, value: str, headers: list[str]) -> int:
        token = value.strip()
        if token.isdigit():
            parsed = int(token)
            if parsed < 1:
                raise ValueError("Google Sheets Search/Update: Column index must be >= 1.")
            return parsed

        if headers:
            lowered = token.lower()
            for idx, header in enumerate(headers, start=1):
                if header.lower() == lowered:
                    return idx

        if cls._is_column_reference(token):
            return cls._column_letter_to_index(token)

        raise ValueError(
            f"Google Sheets Search/Update: Could not resolve column '{value}'. "
            "Use a header name, column letter (A, B, C...), or column number."
        )

    @staticmethod
    def _is_column_reference(value: str) -> bool:
        token = str(value or "").strip()
        return bool(re.fullmatch(r"[A-Za-z]{1,3}", token))

    @classmethod
    def _write_header_row(
        cls,
        *,
        service: Any,
        spreadsheet_id: str,
        sheet_name: str,
        headers: list[str],
    ) -> None:
        if not headers:
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
