from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import SignupRequest


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def signup(self, payload: SignupRequest) -> User:
        existing_user = await self.db.scalar(
            select(User).where(
                or_(User.email == payload.email, User.username == payload.username)
            )
        )
        if existing_user is not None:
            if existing_user.email == payload.email:
                raise ValueError("Email already registered")
            raise ValueError("Username already registered")

        user = User(
            email=payload.email,
            username=payload.username,
            hashed_password=get_password_hash(payload.password),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def login(self, username: str, password: str) -> TokenPair:
        # Check user by email OR username (recommended)
        user = await self.db.scalar(
            select(User).where(
                or_(User.email == username, User.username == username)
            )
        )

        if user is None or not verify_password(password, user.hashed_password):
            raise ValueError("Invalid email or password")

        subject = str(user.id)
        return TokenPair(
            access_token=create_access_token({"sub": subject}),
            refresh_token=create_refresh_token({"sub": subject}),
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenPair:
        payload = decode_refresh_token(refresh_token)
        subject = payload.get("sub")
        if not subject:
            raise ValueError("Invalid refresh token")

        try:
            user_id = UUID(str(subject))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid refresh token") from exc

        user = await self.db.scalar(select(User).where(User.id == user_id))
        if user is None:
            raise ValueError("Invalid refresh token")

        refreshed_subject = str(user.id)
        return TokenPair(
            access_token=create_access_token({"sub": refreshed_subject}),
            refresh_token=create_refresh_token({"sub": refreshed_subject}),
        )
