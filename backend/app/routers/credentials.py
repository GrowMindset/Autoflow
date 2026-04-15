from __future__ import annotations

from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.credentials import (
    AppCredentialCreate,
    AppCredentialDeleteResponse,
    AppCredentialListResponse,
    AppCredentialResponse,
)
from app.services.credential_service import CredentialService

router = APIRouter(prefix="/credentials", tags=["credentials"])

def get_credential_service(db: AsyncSession = Depends(get_db)) -> CredentialService:
    return CredentialService(db)

@router.post("", response_model=AppCredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credential(
    payload: AppCredentialCreate,
    current_user: User = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> AppCredentialResponse:
    try:
        credential = await service.create_credential(current_user.id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return AppCredentialResponse.model_validate(credential)

@router.get("", response_model=AppCredentialListResponse)
async def list_credentials(
    app_name: str | None = None,
    current_user: User = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> AppCredentialListResponse:
    credentials = await service.get_user_credentials(current_user.id, app_name)
    return AppCredentialListResponse(
        credentials=[AppCredentialResponse.model_validate(c) for c in credentials]
    )

@router.get("/{credential_id}", response_model=AppCredentialResponse)
async def get_credential(
    credential_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> AppCredentialResponse:
    credential = await service.get_credential(current_user.id, credential_id)
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )
    return AppCredentialResponse.model_validate(credential)


@router.delete("/{credential_id}", response_model=AppCredentialDeleteResponse)
async def delete_credential(
    credential_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> AppCredentialDeleteResponse:
    deleted = await service.delete_credential(current_user.id, credential_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )
    return AppCredentialDeleteResponse(message="Credential removed successfully")
