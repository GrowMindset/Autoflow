from __future__ import annotations

from typing import Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential import AppCredential
from app.schemas.credentials import AppCredentialCreate
from app.core.security import encrypt_data, decrypt_data


SENSITIVE_TOKEN_FIELDS = {"api_key", "bot_token", "chat_id", "botToken", "chatId"}


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
