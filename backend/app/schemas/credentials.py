from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AppCredentialCreate(BaseModel):
    app_name: str = Field(min_length=1, max_length=50)
    token_data: dict[str, Any]
    description: str | None = Field(default=None, max_length=300)


class AppCredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    app_name: str
    created_at: datetime
    provider: str | None = None
    display_name: str | None = None
    description: str | None = None


class AppCredentialListResponse(BaseModel):
    credentials: list[AppCredentialResponse]


class AppCredentialDeleteResponse(BaseModel):
    message: str


class GoogleOAuthStartResponse(BaseModel):
    auth_url: str
    state: str
    redirect_uri: str
    app_name: str
    scopes: list[str]


class GoogleOAuthExchangeRequest(BaseModel):
    code: str = Field(min_length=1)
    state: str = Field(min_length=1)
    redirect_uri: str | None = None
