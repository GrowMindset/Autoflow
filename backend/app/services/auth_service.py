from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest


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

    async def login(self, payload: LoginRequest) -> str:
        user = await self.db.scalar(select(User).where(User.email == payload.email))
        if user is None or not verify_password(payload.password, user.hashed_password):
            raise ValueError("Invalid email or password")
        return create_access_token({"sub": str(user.id)})
