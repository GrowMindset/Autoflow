from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import DecodeError, ExpiredSignatureError, InvalidTokenError, decode, encode
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User

load_dotenv()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


class BcryptContext:
    def hash(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )


bcrypt_context = BcryptContext()


def _settings() -> tuple[str, str, int, int]:
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    refresh_token_expire_minutes = int(
        os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", "10080")
    )
    if not secret_key:
        raise RuntimeError("SECRET_KEY is not set. Add it to your .env file.")
    return (
        secret_key,
        algorithm,
        access_token_expire_minutes,
        refresh_token_expire_minutes,
    )


def get_password_hash(password: str) -> str:
    return bcrypt_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt_context.verify(plain_password, hashed_password)


def _create_token(
    payload: Mapping[str, object],
    *,
    token_type: str,
    default_expire_minutes: int,
    expires_delta: timedelta | None = None,
) -> str:
    secret_key, algorithm, _, _ = _settings()
    expire_at = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=default_expire_minutes)
    )
    body = dict(payload)
    body.update(
        {
            "exp": expire_at,
            "iat": datetime.now(timezone.utc),
            "type": token_type,
        }
    )
    return encode(body, secret_key, algorithm=algorithm)


def create_access_token(
    payload: Mapping[str, object],
    expires_delta: timedelta | None = None,
) -> str:
    _, _, access_token_expire_minutes, _ = _settings()
    return _create_token(
        payload,
        token_type="access",
        default_expire_minutes=access_token_expire_minutes,
        expires_delta=expires_delta,
    )


def create_refresh_token(
    payload: Mapping[str, object],
    expires_delta: timedelta | None = None,
) -> str:
    _, _, _, refresh_token_expire_minutes = _settings()
    return _create_token(
        payload,
        token_type="refresh",
        default_expire_minutes=refresh_token_expire_minutes,
        expires_delta=expires_delta,
    )


def _decode_token(token: str) -> dict[str, object]:
    secret_key, algorithm, _, _ = _settings()
    try:
        payload = decode(token, secret_key, algorithms=[algorithm])
    except (ExpiredSignatureError, DecodeError, InvalidTokenError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return payload


def decode_access_token(token: str) -> dict[str, object]:
    payload = _decode_token(token)
    token_type = str(payload.get("type") or "").strip().lower()
    # Backward compatibility: allow legacy access tokens without `type`.
    if token_type and token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return payload


def decode_refresh_token(token: str) -> dict[str, object]:
    payload = _decode_token(token)
    token_type = str(payload.get("type") or "").strip().lower()
    if token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return payload


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    payload = decode_access_token(token)
    subject = payload.get("sub")
    try:
        user_id = UUID(str(subject))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        ) from exc

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return user
