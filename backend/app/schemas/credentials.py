from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AppCredentialCreate(BaseModel):
    app_name: str = Field(min_length=1, max_length=50)
    token_data: dict[str, Any]


class AppCredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    app_name: str
    created_at: datetime


class AppCredentialListResponse(BaseModel):
    credentials: list[AppCredentialResponse]


class AppCredentialDeleteResponse(BaseModel):
    message: str
