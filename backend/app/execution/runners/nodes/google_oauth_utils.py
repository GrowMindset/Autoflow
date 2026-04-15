from __future__ import annotations

import os
from typing import Any

from google.oauth2.credentials import Credentials as UserCredentials


GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def is_google_oauth_credential(credential_data: dict[str, Any]) -> bool:
    provider = str(credential_data.get("provider") or "").strip().lower()
    if provider == "google_oauth":
        return True
    return bool(credential_data.get("access_token") or credential_data.get("refresh_token"))


def build_google_user_credentials(
    *,
    credential_data: dict[str, Any],
    required_scopes: list[str],
    integration_name: str,
) -> UserCredentials:
    access_token = str(credential_data.get("access_token") or "").strip() or None
    refresh_token = str(credential_data.get("refresh_token") or "").strip() or None
    if not access_token and not refresh_token:
        raise ValueError(
            f"{integration_name}: OAuth credential is missing access_token/refresh_token."
        )

    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            f"{integration_name}: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not configured."
        )

    return UserCredentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=required_scopes,
    )
