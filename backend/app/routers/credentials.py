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
    GoogleOAuthExchangeRequest,
    GoogleOAuthStartResponse,
)
from app.services.credential_service import CredentialService
from app.services.google_oauth_service import GoogleOAuthService

router = APIRouter(prefix="/credentials", tags=["credentials"])

def get_credential_service(db: AsyncSession = Depends(get_db)) -> CredentialService:
    return CredentialService(db)


def get_google_oauth_service() -> GoogleOAuthService:
    return GoogleOAuthService()


def _to_response(
    *,
    service: CredentialService,
    credential: Any,
) -> AppCredentialResponse:
    summary = service.summarize_credential(credential)
    return AppCredentialResponse(
        id=credential.id,
        user_id=credential.user_id,
        app_name=credential.app_name,
        created_at=credential.created_at,
        provider=summary.get("provider"),
        display_name=summary.get("display_name"),
        description=summary.get("description"),
    )


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
    return _to_response(service=service, credential=credential)

@router.get("", response_model=AppCredentialListResponse)
async def list_credentials(
    app_name: str | None = None,
    current_user: User = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> AppCredentialListResponse:
    credentials = await service.get_user_credentials(current_user.id, app_name)
    return AppCredentialListResponse(
        credentials=[_to_response(service=service, credential=c) for c in credentials]
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
    return _to_response(service=service, credential=credential)


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


@router.get("/oauth/google/start", response_model=GoogleOAuthStartResponse)
async def start_google_oauth(
    app_name: str,
    redirect_uri: str | None = None,
    current_user: User = Depends(get_current_user),
    oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
) -> GoogleOAuthStartResponse:
    try:
        result = oauth_service.build_auth_url(
            app_name=app_name,
            user_id=current_user.id,
            redirect_uri=redirect_uri,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return GoogleOAuthStartResponse(**result)


@router.post("/oauth/google/exchange", response_model=AppCredentialResponse)
async def exchange_google_oauth(
    payload: GoogleOAuthExchangeRequest,
    current_user: User = Depends(get_current_user),
    credential_service: CredentialService = Depends(get_credential_service),
    oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
) -> AppCredentialResponse:
    try:
        state_payload = oauth_service.parse_state(payload.state)
        if str(state_payload.get("sub") or "") != str(current_user.id):
            raise ValueError("Google OAuth state does not belong to current user.")

        app_name = str(state_payload.get("app_name") or "")
        redirect_uri = payload.redirect_uri or str(state_payload.get("redirect_uri") or "")
        if not redirect_uri:
            redirect_uri = oauth_service.resolve_redirect_uri(None)

        token_data = await oauth_service.exchange_code(
            code=payload.code,
            redirect_uri=redirect_uri,
            app_name=app_name,
        )
        credential = await credential_service.create_credential(
            current_user.id,
            AppCredentialCreate(app_name=app_name, token_data=token_data),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_response(service=credential_service, credential=credential)
