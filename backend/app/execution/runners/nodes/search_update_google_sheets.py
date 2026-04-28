"""Google Sheets row/column operations runner using Google OAuth credentials."""

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

SUPPORTED_OPERATIONS = {
    "append_row",
    "delete_rows",
    "overwrite_row",
    "upsert_row",
    "add_columns",
    "delete_columns",
}

OPERATION_ALIASES = {
    "append": "append_row",
    "append_rows": "append_row",
    "add_row": "append_row",
    "add_rows": "append_row",
    "delete": "delete_rows",
    "delete_row": "delete_rows",
    "remove_row": "delete_rows",
    "remove_rows": "delete_rows",
    "overwrite": "overwrite_row",
    "override": "overwrite_row",
    "update": "overwrite_row",
    "upsert": "upsert_row",
    "add_column": "add_columns",
    "create_columns": "add_columns",
    "delete_column": "delete_columns",
    "remove_column": "delete_columns",
    "remove_columns": "delete_columns",
}


class SearchUpdateGoogleSheetsRunner:
    """Performs row and column operations in Google Sheets."""

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
                "Google Sheets: selected credential is not Google OAuth. Reconnect using Google OAuth."
            )

        spreadsheet_id = self._resolve_spreadsheet_id(config)
        sheet_name = str(config.get("sheet_name") or "Sheet1").strip()
        operation = self._normalize_operation(config)
        auto_create_headers = self._coerce_bool(config.get("auto_create_headers"), default=True)

        key_column = str(config.get("key_column") or config.get("search_column") or "").strip()
        key_value = str(config.get("key_value") or config.get("search_value") or "").strip()

        update_pairs = self._collect_update_pairs(config)
        append_pairs = self._collect_append_pairs(config)
        ensure_columns = self._collect_ensure_columns(config.get("ensure_columns"))
        columns_to_add = self._collect_ensure_columns(config.get("columns_to_add"))
        columns_to_delete = self._collect_ensure_columns(config.get("columns_to_delete"))

        if not sheet_name:
            raise ValueError("Google Sheets: 'sheet_name' is required.")

        service = self._build_sheets_service(credential_data)
        sheet_name = self._safe_google_call(
            "Could not resolve sheet name",
            lambda: self._resolve_sheet_name(service, spreadsheet_id, sheet_name),
        )

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)

        result.update(
            {
                "google_sheets_auth_mode": "oauth",
                "google_sheets_spreadsheet_id": spreadsheet_id,
                "google_sheets_sheet_name": sheet_name,
                "google_sheets_operation": operation,
            }
        )

        if operation == "add_columns":
            if not columns_to_add and ensure_columns:
                columns_to_add = ensure_columns
            if not columns_to_add:
                raise ValueError("Google Sheets: 'columns_to_add' is required for add_columns.")

            headers = self._safe_google_call(
                "Could not read sheet headers",
                lambda: self._fetch_header_row(service, spreadsheet_id, sheet_name),
            )
            existing_lower = {str(h or "").strip().lower() for h in headers if str(h or "").strip()}
            next_headers = self._ensure_headers(
                service=service,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                headers=headers,
                search_column="",
                update_columns=[],
                ensure_columns=columns_to_add,
                input_data=input_data,
                auto_create_headers=True,
            )
            added = [
                column
                for column in columns_to_add
                if column.lower() not in existing_lower
            ]
            result.update(
                {
                    "google_sheets_updated": bool(added),
                    "google_sheets_columns_added": added,
                    "google_sheets_headers": next_headers,
                }
            )
            return result

        if operation == "delete_columns":
            if not columns_to_delete:
                raise ValueError("Google Sheets: 'columns_to_delete' is required for delete_columns.")

            headers = self._safe_google_call(
                "Could not read sheet headers",
                lambda: self._fetch_header_row(service, spreadsheet_id, sheet_name),
            )
            if not headers:
                raise ValueError(
                    "Google Sheets: Cannot delete columns because header row is empty."
                )

            sheet_id = self._safe_google_call(
                "Could not resolve sheet metadata",
                lambda: self._fetch_sheet_id(service, spreadsheet_id, sheet_name),
            )
            unique_indexes = sorted(
                {
                    self._resolve_column_index(column_token, headers)
                    for column_token in columns_to_delete
                },
                reverse=True,
            )
            requests = [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": int(col_index) - 1,
                            "endIndex": int(col_index),
                        }
                    }
                }
                for col_index in unique_indexes
            ]
            if requests:
                self._safe_google_call(
                    "Could not delete requested columns",
                    lambda: service.spreadsheets()
                    .batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body={"requests": requests},
                    )
                    .execute(),
                )

            result.update(
                {
                    "google_sheets_updated": bool(requests),
                    "google_sheets_columns_deleted": columns_to_delete,
                    "google_sheets_deleted_column_count": len(requests),
                }
            )
            return result

        if operation in {"overwrite_row", "upsert_row", "delete_rows"}:
            if not key_column:
                raise ValueError(
                    f"Google Sheets: 'key_column' is required for {operation}."
                )
            if key_value == "":
                raise ValueError(
                    f"Google Sheets: 'key_value' is required for {operation}."
                )

        if operation in {"overwrite_row", "upsert_row"}:
            if not update_pairs:
                # Append columns/values can be reused as update mappings.
                update_pairs = append_pairs
            if not update_pairs:
                raise ValueError(
                    "Google Sheets: Provide update_mappings (or append_columns/append_values) for row update operations."
                )

        if operation == "append_row":
            # Prefer update_mappings for append so UI behavior matches overwrite/upsert.
            working_pairs = update_pairs or append_pairs
            if not working_pairs:
                raise ValueError(
                    "Google Sheets: Provide update_mappings (or append_columns/append_values) for append_row."
                )

            headers = self._safe_google_call(
                "Could not read sheet headers",
                lambda: self._fetch_header_row(service, spreadsheet_id, sheet_name),
            )
            columns_from_pairs = [pair["column"] for pair in working_pairs]
            headers = self._ensure_headers(
                service=service,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                headers=headers,
                search_column="",
                update_columns=columns_from_pairs,
                ensure_columns=[*ensure_columns, *columns_to_add],
                input_data=input_data,
                auto_create_headers=auto_create_headers,
            )
            resolved_pairs = self._resolve_pairs_by_index(working_pairs, headers)
            if not resolved_pairs:
                raise ValueError("Google Sheets: Could not resolve append columns.")

            row_width = max(int(pair["index"]) for pair in resolved_pairs)
            new_row = [""] * row_width
            for pair in resolved_pairs:
                new_row[int(pair["index"]) - 1] = self._to_sheet_cell_value(pair.get("value"))

            append_range = self._build_a1_range(
                sheet_name, f"A2:{self._index_to_column_letter(row_width)}"
            )
            append_response = self._safe_google_call(
                "Failed to append row",
                lambda: service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=append_range,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [new_row]},
                )
                .execute(),
            )
            append_updates = append_response.get("updates") if isinstance(append_response, dict) else {}
            result.update(
                {
                    "google_sheets_updated": True,
                    "google_sheets_appended": True,
                    "google_sheets_update_mappings": [
                        {
                            "column": pair["column"],
                            "column_index": pair["index"],
                            "value": pair.get("value"),
                        }
                        for pair in resolved_pairs
                    ],
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

        # Row matching operations: delete_rows / overwrite_row / upsert_row
        headers = self._safe_google_call(
            "Could not read sheet headers",
            lambda: self._fetch_header_row(service, spreadsheet_id, sheet_name),
        )

        if operation in {"overwrite_row", "upsert_row"}:
            columns_from_updates = [pair["column"] for pair in update_pairs]
            headers = self._ensure_headers(
                service=service,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                headers=headers,
                search_column=key_column,
                update_columns=columns_from_updates,
                ensure_columns=[*ensure_columns, *columns_to_add],
                input_data=input_data,
                auto_create_headers=auto_create_headers,
            )

        search_col_index = self._resolve_column_index(key_column, headers)

        resolved_updates: list[dict[str, Any]] = []
        max_update_col_index = search_col_index
        if operation in {"overwrite_row", "upsert_row"}:
            resolved_updates = self._resolve_pairs_by_index(update_pairs, headers)
            if not resolved_updates:
                raise ValueError("Google Sheets: Could not resolve update mappings.")
            max_update_col_index = max(int(item["index"]) for item in resolved_updates)

        max_col_index = max(search_col_index, max_update_col_index)
        data_range = self._build_a1_range(
            sheet_name, f"A2:{self._index_to_column_letter(max_col_index)}"
        )
        rows_response = self._safe_google_call(
            "Could not read row data",
            lambda: service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=data_range)
            .execute(),
        )
        rows = rows_response.get("values") or []

        matches: list[tuple[int, list[Any]]] = []
        for row_offset, row in enumerate(rows, start=2):
            current = row[search_col_index - 1] if len(row) >= search_col_index else ""
            if str(current).strip() == key_value:
                matches.append((row_offset, row))

        if operation == "delete_rows":
            if not matches:
                result.update(
                    {
                        "google_sheets_updated": False,
                        "google_sheets_found": False,
                        "google_sheets_rows_deleted": 0,
                        "google_sheets_search_column": key_column,
                        "google_sheets_search_value": key_value,
                    }
                )
                return result

            sheet_id = self._safe_google_call(
                "Could not resolve sheet metadata",
                lambda: self._fetch_sheet_id(service, spreadsheet_id, sheet_name),
            )
            delete_requests = [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row_number - 1,
                            "endIndex": row_number,
                        }
                    }
                }
                for row_number, _ in sorted(matches, key=lambda item: item[0], reverse=True)
            ]
            self._safe_google_call(
                "Failed to delete matching rows",
                lambda: service.spreadsheets()
                .batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": delete_requests},
                )
                .execute(),
            )

            result.update(
                {
                    "google_sheets_updated": True,
                    "google_sheets_found": True,
                    "google_sheets_rows_deleted": len(matches),
                    "google_sheets_search_column": key_column,
                    "google_sheets_search_value": key_value,
                    "google_sheets_deleted_row_numbers": [row for row, _ in matches],
                }
            )
            return result

        # overwrite_row / upsert_row
        mappings_meta = [
            {
                "column": item["column"],
                "column_index": item["index"],
                "value": item.get("value"),
            }
            for item in resolved_updates
        ]
        primary_update = resolved_updates[0]

        if not matches:
            if operation == "upsert_row":
                row_width = max_col_index
                new_row = [""] * row_width
                new_row[search_col_index - 1] = self._to_sheet_cell_value(key_value)
                for item in resolved_updates:
                    new_row[int(item["index"]) - 1] = self._to_sheet_cell_value(item.get("value"))

                append_range = self._build_a1_range(
                    sheet_name, f"A2:{self._index_to_column_letter(row_width)}"
                )
                append_response = self._safe_google_call(
                    "Failed to append row for missing key",
                    lambda: service.spreadsheets()
                    .values()
                    .append(
                        spreadsheetId=spreadsheet_id,
                        range=append_range,
                        valueInputOption="USER_ENTERED",
                        insertDataOption="INSERT_ROWS",
                        body={"values": [new_row]},
                    )
                    .execute(),
                )
                append_updates = append_response.get("updates") if isinstance(append_response, dict) else {}
                result.update(
                    {
                        "google_sheets_updated": True,
                        "google_sheets_found": False,
                        "google_sheets_upserted": True,
                        "google_sheets_search_column": key_column,
                        "google_sheets_search_value": key_value,
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
                    "google_sheets_search_column": key_column,
                    "google_sheets_search_value": key_value,
                    "google_sheets_update_mappings": mappings_meta,
                }
            )
            return result

        matched_row_number, matched_row_values = matches[0]
        row_width = max_col_index
        merged_row = list(matched_row_values or [])
        if len(merged_row) < row_width:
            merged_row.extend([""] * (row_width - len(merged_row)))
        merged_row[search_col_index - 1] = self._to_sheet_cell_value(key_value)
        for item in resolved_updates:
            merged_row[int(item["index"]) - 1] = self._to_sheet_cell_value(item.get("value"))

        update_range = self._build_a1_range(
            sheet_name,
            (
                f"A{matched_row_number}:"
                f"{self._index_to_column_letter(row_width)}{matched_row_number}"
            ),
        )
        update_response = self._safe_google_call(
            "Failed to update matched row",
            lambda: service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=update_range,
                valueInputOption="USER_ENTERED",
                body={"values": [merged_row[:row_width]]},
            )
            .execute(),
        )

        result.update(
            {
                "google_sheets_updated": True,
                "google_sheets_found": True,
                "google_sheets_auth_mode": "oauth",
                "google_sheets_search_column": key_column,
                "google_sheets_search_value": key_value,
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
            raise ValueError("Google Sheets: 'credential_id' is required.")

        all_credential_data: dict[str, Any] = context.get("resolved_credential_data") or {}
        raw_data = all_credential_data.get(str(cred_id))
        if not isinstance(raw_data, dict):
            raise ValueError(
                "Google Sheets: Credential not found. Save a Sheets credential and select it in this node."
            )
        return raw_data

    @staticmethod
    def _build_sheets_service(credential_data: dict[str, Any]) -> Any:
        user_credentials = build_google_user_credentials(
            credential_data=credential_data,
            required_scopes=GOOGLE_SHEETS_SCOPES,
            integration_name="Google Sheets",
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
                "Google Sheets: Google credential authentication failed. Reconnect OAuth credential."
            ) from exc
        except HttpError as exc:
            google_error = cls._extract_google_error(exc)
            if exc.resp is not None and int(getattr(exc.resp, "status", 0) or 0) == 403:
                raise ValueError(
                    "Google Sheets: Permission denied (403) while using Google OAuth. "
                    f"Google said: {google_error}. "
                    "Reconnect Sheets OAuth credential, ensure this account is allowed in OAuth test users, and verify Sheets/Drive APIs are enabled."
                ) from exc
            raise ValueError(f"Google Sheets: {action}: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"Google Sheets: {action}: {exc}") from exc

    @classmethod
    def _fetch_header_row(cls, service: Any, spreadsheet_id: str, sheet_name: str) -> list[str]:
        response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=cls._build_a1_range(sheet_name, "1:1"))
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
    def _fetch_sheet_id(service: Any, spreadsheet_id: str, sheet_name: str) -> int:
        response = (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(sheetId,title))")
            .execute()
        )
        lowered = sheet_name.lower()
        fallback_id: int | None = None
        available_titles: list[str] = []
        for sheet in response.get("sheets") or []:
            properties = sheet.get("properties") or {}
            title = str(properties.get("title") or "")
            if title:
                available_titles.append(title)
            if title == sheet_name:
                sheet_id = properties.get("sheetId")
                if isinstance(sheet_id, int):
                    return sheet_id
                break
            if title.lower() == lowered and fallback_id is None:
                maybe_id = properties.get("sheetId")
                if isinstance(maybe_id, int):
                    fallback_id = maybe_id
        if fallback_id is not None:
            return fallback_id
        available = ", ".join(available_titles[:10])
        if len(available_titles) > 10:
            available = f"{available}, ..."
        if available:
            raise ValueError(
                f"Sheet '{sheet_name}' was not found in spreadsheet metadata. Available sheets: {available}"
            )
        raise ValueError(f"Sheet '{sheet_name}' was not found in spreadsheet metadata.")

    @staticmethod
    def _normalize_sheet_name_value(sheet_name: str) -> str:
        return str(sheet_name or "").strip()

    @classmethod
    def _resolve_sheet_name(cls, service: Any, spreadsheet_id: str, sheet_name: str) -> str:
        requested = cls._normalize_sheet_name_value(sheet_name)
        if not requested:
            raise ValueError("Google Sheets: 'sheet_name' is required.")

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
            raise ValueError("Google Sheets: No sheets found in spreadsheet metadata.")

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
            f"Google Sheets: Sheet '{requested}' was not found. Available sheets: {available}"
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
            if normalized in {"0", "false", "no", "off", ""}:
                return False
        return bool(raw_value)

    @staticmethod
    def _to_sheet_cell_value(value: Any) -> str | int | float | bool:
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return ", ".join(
                str(item)
                for item in value
                if item is not None and str(item).strip()
            )
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, default=str)
        return str(value)

    @classmethod
    def _normalize_operation(cls, config: dict[str, Any]) -> str:
        explicit = str(config.get("operation") or "").strip().lower()
        if explicit:
            normalized = OPERATION_ALIASES.get(explicit, explicit)
            if normalized not in SUPPORTED_OPERATIONS:
                raise ValueError(
                    "Google Sheets: Unsupported operation. "
                    f"Supported: {', '.join(sorted(SUPPORTED_OPERATIONS))}."
                )
            return normalized

        # Backward-compatible behavior: old node searched + updated one row,
        # optionally appending if no match.
        upsert_if_not_found = cls._coerce_bool(config.get("upsert_if_not_found"), default=False)
        return "upsert_row" if upsert_if_not_found else "overwrite_row"

    @classmethod
    def _resolve_spreadsheet_id(cls, config: dict[str, Any]) -> str:
        source_type = str(config.get("spreadsheet_source_type") or "id").strip().lower()
        spreadsheet_id = str(config.get("spreadsheet_id") or "").strip()
        spreadsheet_url = str(config.get("spreadsheet_url") or "").strip()

        if source_type == "url":
            if not spreadsheet_url:
                raise ValueError("Google Sheets: 'spreadsheet_url' is required when source type is url.")
            parsed = cls._extract_spreadsheet_id_from_url(spreadsheet_url)
            if not parsed:
                raise ValueError("Google Sheets: Could not parse spreadsheet ID from spreadsheet_url.")
            return parsed

        if spreadsheet_id:
            return spreadsheet_id

        if spreadsheet_url:
            parsed = cls._extract_spreadsheet_id_from_url(spreadsheet_url)
            if parsed:
                return parsed

        raise ValueError("Google Sheets: 'spreadsheet_id' is required.")

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
    def _collect_append_pairs(cls, config: dict[str, Any]) -> list[dict[str, Any]]:
        raw_columns = config.get("append_columns")
        raw_values = config.get("append_values")
        if not isinstance(raw_columns, list) or not raw_columns:
            return []

        values = raw_values if isinstance(raw_values, list) else []
        pairs: list[dict[str, Any]] = []
        for idx, raw_column in enumerate(raw_columns):
            column = str(raw_column or "").strip()
            if not column:
                continue
            value = values[idx] if idx < len(values) else ""
            pairs.append({"column": column, "value": value})
        return pairs

    @staticmethod
    def _collect_ensure_columns(raw_columns: Any) -> list[str]:
        if not isinstance(raw_columns, list):
            return []

        seen_lower: set[str] = set()
        ensured: list[str] = []
        for item in raw_columns:
            token = str(item or "").strip()
            if not token:
                continue
            lowered = token.lower()
            if lowered in seen_lower:
                continue
            seen_lower.add(lowered)
            ensured.append(token)
        return ensured

    @classmethod
    def _resolve_pairs_by_index(
        cls,
        pairs: list[dict[str, Any]],
        headers: list[str],
    ) -> list[dict[str, Any]]:
        resolved_by_index: dict[int, dict[str, Any]] = {}
        for pair in pairs:
            column = str(pair.get("column") or "").strip()
            if not column:
                continue
            col_index = cls._resolve_column_index(column, headers)
            resolved_by_index[col_index] = {
                "column": column,
                "index": col_index,
                "value": pair.get("value"),
            }
        return sorted(resolved_by_index.values(), key=lambda item: int(item["index"]))

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
        ensure_columns: list[str],
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

        if search_column and not cls._is_column_reference(search_column):
            _add_header(search_column)

        for update_column in update_columns:
            if not cls._is_column_reference(update_column):
                _add_header(update_column)

        for ensured_column in ensure_columns:
            if not cls._is_column_reference(ensured_column):
                _add_header(ensured_column)

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
                raise ValueError("Google Sheets: Column index must be >= 1.")
            return parsed

        if headers:
            lowered = token.lower()
            for idx, header in enumerate(headers, start=1):
                if header.lower() == lowered:
                    return idx

        if cls._is_column_reference(token):
            return cls._column_letter_to_index(token)

        raise ValueError(
            f"Google Sheets: Could not resolve column '{value}'. "
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
        target_range = cls._build_a1_range(sheet_name, f"A1:{end_col}1")
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

    @classmethod
    def _build_a1_range(cls, sheet_name: str, suffix: str) -> str:
        return f"{cls._quote_sheet_name(sheet_name)}!{str(suffix or '').strip()}"

    @staticmethod
    def _quote_sheet_name(sheet_name: str) -> str:
        token = str(sheet_name or "").strip()
        escaped = token.replace("'", "''")
        return f"'{escaped}'"

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
