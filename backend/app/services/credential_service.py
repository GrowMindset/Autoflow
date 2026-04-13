from __future__ import annotations

from typing import Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential import AppCredential
from app.schemas.credentials import AppCredentialCreate
from app.core.security import encrypt_data, decrypt_data

class CredentialService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_credential(self, user_id: UUID, payload: AppCredentialCreate) -> AppCredential:
        # Encrypt specific fields within token_data if necessary, 
        # or encrypt the whole JSON if it contains sensitive keys.
        # For simplicity and security, we'll assume token_data has an 'api_key'
        # and we will encrypt it.
        
        token_data = dict(payload.token_data)
        if "api_key" in token_data:
            token_data["api_key"] = encrypt_data(token_data["api_key"])
        
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

    def get_decrypted_api_key(self, credential: AppCredential) -> str | None:
        api_key_encrypted = credential.token_data.get("api_key")
        if api_key_encrypted:
            return decrypt_data(api_key_encrypted)
        return None
