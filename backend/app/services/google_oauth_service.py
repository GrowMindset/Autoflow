from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse
from urllib.parse import urlencode
from uuid import UUID

import httpx
from jwt import DecodeError, ExpiredSignatureError, InvalidTokenError, decode, encode


GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_DEFAULT_REDIRECT_PATH = "/app/oauth/google/callback"
SUPPORTED_GOOGLE_APPS = {"gmail", "sheets", "docs"}
GOOGLE_LEGACY_CALLBACK_SUFFIXES = (
    "/app/oauth/gmail/callback",
    "/app/oauth/sheets/callback",
    "/app/oauth/docs/callback",
)
SHARED_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]
APP_SCOPES: dict[str, list[str]] = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ],
    "sheets": [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
    "docs": [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ],
}


class GoogleOAuthService:
    def __init__(self) -> None:
        self.client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        self.client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
        self.default_redirect_uri = (
            os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or ""
        ).strip()
        self.frontend_base_url = (
            os.getenv("FRONTEND_BASE_URL") or "http://localhost:5173"
        ).rstrip("/")
        self.jwt_secret = (os.getenv("SECRET_KEY") or "").strip()
        self.jwt_algorithm = (os.getenv("ALGORITHM") or "HS256").strip()

    def ensure_configured(self) -> None:
        if not self.client_id:
            raise ValueError("GOOGLE_CLIENT_ID is not configured.")
        if not self.client_secret:
            raise ValueError("GOOGLE_CLIENT_SECRET is not configured.")
        if not self.jwt_secret:
            raise ValueError("SECRET_KEY is not configured.")

    def normalize_app_name(self, app_name: str) -> str:
        normalized = (app_name or "").strip().lower()
        if normalized not in SUPPORTED_GOOGLE_APPS:
            raise ValueError("Google OAuth currently supports app_name 'gmail', 'sheets', and 'docs'.")
        return normalized

    def resolve_redirect_uri(self, redirect_uri: str | None = None) -> str:
        candidate = (redirect_uri or "").strip()
        if candidate:
            return self._normalize_google_redirect_uri(candidate)
        if self.default_redirect_uri:
            return self._normalize_google_redirect_uri(self.default_redirect_uri)
        return self._normalize_google_redirect_uri(
            f"{self.frontend_base_url}{GOOGLE_DEFAULT_REDIRECT_PATH}"
        )

    @staticmethod
    def _normalize_google_redirect_uri(redirect_uri: str) -> str:
        """
        Normalize legacy per-app callback paths to one stable Google callback URL.
        This avoids redirect_uri_mismatch when older clients pass:
        /app/oauth/gmail|sheets|docs/callback.
        """
        parsed = urlparse(redirect_uri)
        path = parsed.path or ""
        if path in GOOGLE_LEGACY_CALLBACK_SUFFIXES:
            parsed = parsed._replace(path=GOOGLE_DEFAULT_REDIRECT_PATH)
            return urlunparse(parsed)
        return redirect_uri

    def get_scopes(self, app_name: str) -> list[str]:
        normalized = self.normalize_app_name(app_name)
        return [*SHARED_SCOPES, *APP_SCOPES[normalized]]

    def build_state(
        self,
        *,
        user_id: UUID,
        app_name: str,
        redirect_uri: str,
    ) -> str:
        self.ensure_configured()
        normalized_app = self.normalize_app_name(app_name)
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "purpose": "google_oauth_connect",
            "sub": str(user_id),
            "app_name": normalized_app,
            "redirect_uri": redirect_uri,
            "iat": now,
            "exp": now + timedelta(minutes=20),
        }
        return encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def parse_state(self, state: str) -> dict[str, Any]:
        self.ensure_configured()
        try:
            payload = decode(state, self.jwt_secret, algorithms=[self.jwt_algorithm])
        except (ExpiredSignatureError, DecodeError, InvalidTokenError) as exc:
            raise ValueError("Google OAuth state is invalid or expired.") from exc

        if payload.get("purpose") != "google_oauth_connect":
            raise ValueError("Google OAuth state purpose mismatch.")
        app_name = self.normalize_app_name(str(payload.get("app_name") or ""))
        payload["app_name"] = app_name
        payload["sub"] = str(payload.get("sub") or "")
        payload["redirect_uri"] = str(payload.get("redirect_uri") or "")
        return payload

    def build_auth_url(
        self,
        *,
        app_name: str,
        user_id: UUID,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_configured()
        normalized_app = self.normalize_app_name(app_name)
        final_redirect_uri = self.resolve_redirect_uri(redirect_uri)
        scopes = self.get_scopes(normalized_app)
        state = self.build_state(
            user_id=user_id,
            app_name=normalized_app,
            redirect_uri=final_redirect_uri,
        )
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": final_redirect_uri,
                "response_type": "code",
                "scope": " ".join(scopes),
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": state,
            }
        )
        return {
            "auth_url": f"{GOOGLE_AUTH_ENDPOINT}?{query}",
            "state": state,
            "redirect_uri": final_redirect_uri,
            "app_name": normalized_app,
            "scopes": scopes,
        }

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        app_name: str,
    ) -> dict[str, Any]:
        self.ensure_configured()
        normalized_app = self.normalize_app_name(app_name)
        scopes = self.get_scopes(normalized_app)

        async with httpx.AsyncClient(timeout=30.0) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        token_payload = token_response.json() if token_response.content else {}
        if token_response.status_code >= 400:
            error_description = token_payload.get("error_description") or token_payload.get("error")
            raise ValueError(f"Google OAuth token exchange failed: {error_description or token_response.text}")

        access_token = str(token_payload.get("access_token") or "").strip()
        refresh_token = str(token_payload.get("refresh_token") or "").strip()
        token_type = str(token_payload.get("token_type") or "Bearer").strip()
        scope = str(token_payload.get("scope") or " ".join(scopes)).strip()
        expires_in = int(token_payload.get("expires_in") or 0)

        if not access_token:
            raise ValueError("Google OAuth token exchange did not return access_token.")

        email = await self.fetch_user_email(access_token)
        credential_data: dict[str, Any] = {
            "provider": "google_oauth",
            "access_token": access_token,
            "token_type": token_type,
            "scope": scope,
            "email": email or "",
        }
        if refresh_token:
            credential_data["refresh_token"] = refresh_token
        if expires_in > 0:
            expiry_epoch = int(datetime.now(timezone.utc).timestamp()) + expires_in
            credential_data["expiry_epoch"] = str(expiry_epoch)
        id_token = str(token_payload.get("id_token") or "").strip()
        if id_token:
            credential_data["id_token"] = id_token

        return credential_data

    async def fetch_user_email(self, access_token: str) -> str:
        if not access_token:
            return ""
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                GOOGLE_USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code >= 400:
            return ""
        payload = response.json() if response.content else {}
        return str(payload.get("email") or "").strip()
