"""Google Sheets create runner using a service account credential."""

from __future__ import annotations

import json
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


GOOGLE_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


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

        title = str(config.get("title") or "").strip()
        if not title:
            raise ValueError("Google Sheets Create: 'title' is required.")

        sheet_name = str(config.get("sheet_name") or "").strip()

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

        result: dict[str, Any] = {}
        if isinstance(input_data, dict):
            result.update(input_data)
        result.update(
            {
                "google_sheets_created": True,
                "google_sheets_spreadsheet_id": created_dict.get("spreadsheetId"),
                "google_sheets_spreadsheet_url": created_dict.get("spreadsheetUrl"),
                "google_sheets_title": created_title or title,
                "google_sheets_sheet_names": sheet_titles,
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
        raw_service_account = (
            credential_data.get("service_account_json")
            or credential_data.get("serviceAccountJson")
        )
        if isinstance(raw_service_account, str):
            try:
                service_account_info = json.loads(raw_service_account)
            except Exception as exc:
                raise ValueError(
                    "Google Sheets Create: service_account_json is not valid JSON."
                ) from exc
        elif isinstance(raw_service_account, dict):
            service_account_info = raw_service_account
        else:
            raise ValueError(
                "Google Sheets Create: service_account_json is missing in selected credential."
            )

        if not isinstance(service_account_info, dict):
            raise ValueError("Google Sheets Create: service account payload must be a JSON object.")

        for required_key in ("client_email", "private_key"):
            if not str(service_account_info.get(required_key) or "").strip():
                raise ValueError(
                    f"Google Sheets Create: service account payload is missing '{required_key}'."
                )

        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=[GOOGLE_SHEETS_SCOPE],
        )
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)
