from __future__ import annotations

import json
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
            token_data.pop("botToken", None)
            token_data.pop("chatId", None)
        elif payload.app_name == "gmail":
            email = (
                token_data.get("email")
                or token_data.get("user_email")
                or token_data.get("username")
            )
            app_password = (
                token_data.get("app_password")
                or token_data.get("password")
                or token_data.get("api_key")
            )

            if not isinstance(email, str) or not email.strip():
                raise ValueError(
                    "Gmail credential requires email (token_data.email)."
                )
            if not isinstance(app_password, str) or not app_password.strip():
                raise ValueError(
                    "Gmail credential requires app_password (token_data.app_password)."
                )

            token_data["email"] = email.strip()
            token_data["app_password"] = app_password.strip()
            token_data["user_email"] = email.strip()
            token_data["username"] = email.strip()
            token_data["password"] = app_password.strip()
        elif payload.app_name == "sheets":
            raw_sa_json = (
                token_data.get("service_account_json")
                or token_data.get("serviceAccountJson")
            )

            if not isinstance(raw_sa_json, str) or not raw_sa_json.strip():
                raise ValueError(
                    "Google Sheets credential requires service account JSON (token_data.service_account_json)."
                )

            try:
                service_account_info = json.loads(raw_sa_json)
            except Exception as exc:
                raise ValueError("Google Sheets service account JSON is invalid.") from exc

            if not isinstance(service_account_info, dict):
                raise ValueError("Google Sheets service account JSON must be an object.")

            client_email = str(service_account_info.get("client_email") or "").strip()
            private_key = str(service_account_info.get("private_key") or "").strip()
            token_uri = str(service_account_info.get("token_uri") or "").strip()

            if not client_email:
                raise ValueError("Google Sheets service account JSON is missing client_email.")
            if not private_key:
                raise ValueError("Google Sheets service account JSON is missing private_key.")

            # Keep a normalized minimal shape so runners don't rely on many alias keys.
            normalized_info = {
                "type": "service_account",
                "client_email": client_email,
                "private_key": private_key,
                "token_uri": token_uri or "https://oauth2.googleapis.com/token",
                "project_id": service_account_info.get("project_id") or "",
                "private_key_id": service_account_info.get("private_key_id") or "",
                "client_id": service_account_info.get("client_id") or "",
            }
            token_data["service_account_json"] = json.dumps(normalized_info)
            token_data.pop("serviceAccountJson", None)
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
