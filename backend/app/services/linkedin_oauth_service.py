from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from jwt import DecodeError, ExpiredSignatureError, InvalidTokenError, decode, encode

LINKEDIN_AUTH_ENDPOINT = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_ENDPOINT = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_ME_ENDPOINT = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_DEFAULT_REDIRECT_PATH = "/app/oauth/linkedin/callback"
LINKEDIN_SCOPES = [
    "openid",
    "profile",
    "email",
    "w_member_social",
]

class LinkedInOAuthService:
    def __init__(self) -> None:
        self.client_id = (os.getenv("LINKEDIN_CLIENT_ID") or "").strip()
        self.client_secret = (os.getenv("LINKEDIN_CLIENT_SECRET") or "").strip()
        self.default_redirect_uri = (
            os.getenv("LINKEDIN_OAUTH_REDIRECT_URI") or ""
        ).strip()
        self.frontend_base_url = (
            os.getenv("FRONTEND_BASE_URL") or "http://localhost:5173"
        ).rstrip("/")
        self.jwt_secret = (os.getenv("SECRET_KEY") or "").strip()
        self.jwt_algorithm = (os.getenv("ALGORITHM") or "HS256").strip()

    def ensure_configured(self) -> None:
        if not self.client_id:
            raise ValueError("LINKEDIN_CLIENT_ID is not configured.")
        if not self.client_secret:
            raise ValueError("LINKEDIN_CLIENT_SECRET is not configured.")
        if not self.jwt_secret:
            raise ValueError("SECRET_KEY is not configured.")

    def resolve_redirect_uri(self, redirect_uri: str | None = None) -> str:
        candidate = (redirect_uri or "").strip()
        if candidate:
            return candidate
        if self.default_redirect_uri:
            return self.default_redirect_uri
        return f"{self.frontend_base_url}{LINKEDIN_DEFAULT_REDIRECT_PATH}"

    def build_state(
        self,
        *,
        user_id: UUID,
        redirect_uri: str,
    ) -> str:
        self.ensure_configured()
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "purpose": "linkedin_oauth_connect",
            "sub": str(user_id),
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
            raise ValueError("LinkedIn OAuth state is invalid or expired.") from exc

        if payload.get("purpose") != "linkedin_oauth_connect":
            raise ValueError("LinkedIn OAuth state purpose mismatch.")
        payload["sub"] = str(payload.get("sub") or "")
        payload["redirect_uri"] = str(payload.get("redirect_uri") or "")
        return payload

    def build_auth_url(
        self,
        *,
        user_id: UUID,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_configured()
        final_redirect_uri = self.resolve_redirect_uri(redirect_uri)
        state = self.build_state(user_id=user_id, redirect_uri=final_redirect_uri)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": final_redirect_uri,
                "scope": " ".join(LINKEDIN_SCOPES),
                "state": state,
                "prompt": "consent",
            }
        )
        return {
            "auth_url": f"{LINKEDIN_AUTH_ENDPOINT}?{query}",
            "state": state,
            "redirect_uri": final_redirect_uri,
            "scopes": LINKEDIN_SCOPES,
        }

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        self.ensure_configured()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                LINKEDIN_TOKEN_ENDPOINT,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            error_description = payload.get("error_description") or payload.get("error")
            raise ValueError(
                f"LinkedIn OAuth token exchange failed: {error_description or response.text}"
            )

        access_token = str(payload.get("access_token") or "").strip()
        expires_in = int(payload.get("expires_in") or 0)
        refresh_token = str(payload.get("refresh_token") or "").strip()

        if not access_token:
            raise ValueError("LinkedIn OAuth token exchange did not return access_token.")

        member_urn = await self.fetch_member_urn(access_token)
        token_data: dict[str, Any] = {
            "provider": "linkedin_oauth",
            "access_token": access_token,
            "api_key": access_token,
            "member_urn": member_urn,
        }

        if refresh_token:
            token_data["refresh_token"] = refresh_token
        if expires_in > 0:
            token_data["expiry_epoch"] = str(int(datetime.now(timezone.utc).timestamp()) + expires_in)

        return token_data

    async def fetch_member_urn(self, access_token: str) -> str:
        if not access_token:
            raise ValueError("LinkedIn access token is required to fetch member profile.")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                LINKEDIN_ME_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )

        payload = response.json() if response.content else {}
        if response.status_code >= 400:
            error_description = payload.get("message") or response.text
            raise ValueError(f"LinkedIn API failed to fetch member profile: {error_description}")

        member_id = str(payload.get("sub") or "").strip()
        if not member_id:
            raise ValueError("LinkedIn API did not return a member id.")

        return f"urn:li:person:{member_id}"
