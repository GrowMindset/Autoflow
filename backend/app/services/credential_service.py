from __future__ import annotations

from typing import Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential import AppCredential
from app.schemas.credentials import AppCredentialCreate
from app.core.security import encrypt_data, decrypt_data


SENSITIVE_TOKEN_FIELDS = {
    "api_key",
    "access_token",
    "bot_token",
    "chat_id",
    "botToken",
    "chatId",
    "app_password",
    "password",
    "email",
    "user_email",
    "username",
    "service_account_json",
    "serviceAccountJson",
    "private_key",
    "privateKey",
    "access_token",
    "refresh_token",
    "id_token",
}


class CredentialService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_credential(self, user_id: UUID, payload: AppCredentialCreate) -> AppCredential:
        token_data = dict(payload.token_data)

        if payload.app_name == "telegram":
            bot_token = (
                token_data.get("api_key")
                or token_data.get("bot_token")
                or token_data.get("botToken")
            )
            chat_id = token_data.get("chat_id") or token_data.get("chatId")

            if not isinstance(bot_token, str) or not bot_token.strip():
                raise ValueError(
                    "Telegram credential requires bot token (token_data.api_key)."
                )
            if not isinstance(chat_id, str) or not chat_id.strip():
                raise ValueError(
                    "Telegram credential requires chat_id (token_data.chat_id)."
                )

            token_data["api_key"] = bot_token.strip()
            token_data["bot_token"] = bot_token.strip()
            token_data["chat_id"] = chat_id.strip()
            token_data["provider"] = "telegram_bot_token"
            token_data.pop("botToken", None)
            token_data.pop("chatId", None)
        elif payload.app_name in {"gmail", "sheets", "docs"}:
            app_label = {
                "gmail": "Gmail",
                "sheets": "Google Sheets",
                "docs": "Google Docs",
            }[payload.app_name]
            provider = str(token_data.get("provider") or "").strip().lower()
            access_token = str(token_data.get("access_token") or "").strip()
            refresh_token = str(token_data.get("refresh_token") or "").strip()

            if provider and provider != "google_oauth":
                raise ValueError(
                    f"{app_label} supports OAuth-only credentials. Connect via Google OAuth."
                )
            if not access_token and not refresh_token:
                raise ValueError(
                    f"{app_label} OAuth credential requires access_token or refresh_token."
                )

            email = str(
                token_data.get("email")
                or token_data.get("user_email")
                or token_data.get("username")
                or ""
            ).strip()

            normalized: dict[str, Any] = {"provider": "google_oauth"}
            if access_token:
                normalized["access_token"] = access_token
            if refresh_token:
                normalized["refresh_token"] = refresh_token

            for passthrough_key in ("token_type", "scope", "expiry_epoch", "id_token"):
                value = token_data.get(passthrough_key)
                if isinstance(value, str) and value.strip():
                    normalized[passthrough_key] = value.strip()
            if email:
                normalized["email"] = email
                normalized["user_email"] = email
                normalized["username"] = email

            token_data = normalized
        elif payload.app_name == "whatsapp":
            access_token = (
                token_data.get("access_token")
                or token_data.get("api_key")
            )
            phone_number_id = token_data.get("phone_number_id")

            if not isinstance(access_token, str) or not access_token.strip():
                raise ValueError(
                    "WhatsApp credential requires access_token (token_data.access_token)."
                )
            if not isinstance(phone_number_id, str) or not phone_number_id.strip():
                raise ValueError(
                    "WhatsApp credential requires phone_number_id (token_data.phone_number_id)."
                )

            token_data["access_token"] = access_token.strip()
            token_data["api_key"] = access_token.strip()  # alias for resolved_credentials
            token_data["phone_number_id"] = phone_number_id.strip()
            waba_id = token_data.get("waba_id")
            if isinstance(waba_id, str) and waba_id.strip():
                token_data["waba_id"] = waba_id.strip()

        for key in SENSITIVE_TOKEN_FIELDS:
            value = token_data.get(key)
            if isinstance(value, str) and value:
                token_data[key] = encrypt_data(value)
        
        credential = AppCredential(
            user_id=user_id,
            app_name=payload.app_name,
            token_data=token_data,
        )
        self.db.add(credential)
        await self.db.commit()
        await self.db.refresh(credential)
        return credential

    async def get_user_credentials(self, user_id: UUID, app_name: str | None = None) -> list[AppCredential]:
        query = select(AppCredential).where(AppCredential.user_id == user_id)
        if app_name:
            query = query.where(AppCredential.app_name == app_name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_credential(self, user_id: UUID, credential_id: UUID) -> AppCredential | None:
        credential = await self.db.get(AppCredential, credential_id)
        if credential and credential.user_id == user_id:
            return credential
        return None

    async def delete_credential(self, user_id: UUID, credential_id: UUID) -> bool:
        credential = await self.get_credential(user_id, credential_id)
        if credential is None:
            return False
        await self.db.delete(credential)
        await self.db.commit()
        return True

    def get_decrypted_api_key(self, credential: AppCredential) -> str | None:
        api_key_encrypted = credential.token_data.get("api_key")
        if api_key_encrypted:
            try:
                return decrypt_data(api_key_encrypted)
            except Exception:
                # Backward compatibility for older plaintext records
                return api_key_encrypted
        return None

    def summarize_credential(self, credential: AppCredential) -> dict[str, str | None]:
        token_data = dict(credential.token_data or {})
        provider = str(token_data.get("provider") or "").strip() or None
        email = self._safe_read_token_value(token_data, "email")
        app_name = str(credential.app_name or "").strip().lower()

        display_name = None
        description = None

        if provider == "google_oauth":
            display_name = "Google OAuth"
            description = f"Connected Google account ({email})" if email else "Connected Google account"
        elif provider == "google_service_account":
            display_name = "Service Account JSON (Legacy)"
            description = "Legacy Google service account key"
        elif provider == "gmail_app_password":
            display_name = "Gmail App Password (Legacy)"
            description = f"Legacy Gmail app password ({email})" if email else "Legacy Gmail app password"
        elif provider == "telegram_bot_token":
            display_name = "Telegram Bot Token"
            description = "Telegram bot token + chat ID"
        elif provider == "api_key":
            display_name = "API Key"
            description = f"{app_name.title()} API key" if app_name else "API key"
        elif provider:
            display_name = provider.replace("_", " ").title()
            description = f"{app_name.title()} credential" if app_name else "Credential"
        else:
            display_name = app_name.title() if app_name else "Credential"
            description = f"{display_name} credential"

        return {
            "provider": provider,
            "display_name": display_name,
            "description": description,
        }

    @staticmethod
    def _safe_read_token_value(token_data: dict[str, Any], key: str) -> str | None:
        raw_value = token_data.get(key)
        if not isinstance(raw_value, str) or not raw_value:
            return None
        try:
            value = decrypt_data(raw_value)
        except Exception:
            value = raw_value
        value = str(value).strip()
        return value or None
