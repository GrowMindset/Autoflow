from __future__ import annotations

import os
import unittest
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import decode_access_token, decode_refresh_token, verify_password
from app.core.database import get_db
from app.main import app
from app.models import Base
from app.models.user import User
from test.asgi_client import ASGITestClient


class AuthEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            self.fail("DATABASE_URL is required to run auth endpoint tests")

        self.schema_name = f"auth_test_{uuid4().hex}"
        self.admin_engine = create_async_engine(database_url, future=True)
        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema_name}"'))

        self.engine = create_async_engine(
            database_url,
            future=True,
            connect_args={"server_settings": {"search_path": self.schema_name}},
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

        async def override_get_db() -> AsyncSession:
            async with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        self.client = ASGITestClient(app)

    async def asyncTearDown(self) -> None:
        app.dependency_overrides.clear()
        await self.engine.dispose()
        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{self.schema_name}" CASCADE'))
        await self.admin_engine.dispose()

    async def _create_user(self, *, email: str, username: str, hashed_password: str) -> User:
        async with self.session_factory() as session:
            user = User(email=email, username=username, hashed_password=hashed_password)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def test_signup_creates_user_and_hashes_password(self) -> None:
        status_code, payload = await self.client.post(
            "/auth/signup",
            json_body={
                "email": "ishika@example.com",
                "username": "ishika",
                "password": "mypassword123",
            },
        )

        self.assertEqual(status_code, 201)
        self.assertEqual(payload["email"], "ishika@example.com")
        self.assertEqual(payload["username"], "ishika")
        self.assertIn("id", payload)
        self.assertNotIn("hashed_password", payload)

        async with self.session_factory() as session:
            user = await session.get(User, payload["id"])
            self.assertIsNotNone(user)
            assert user is not None
            self.assertNotEqual(user.hashed_password, "mypassword123")
            self.assertTrue(verify_password("mypassword123", user.hashed_password))

    async def test_signup_rejects_duplicate_email_and_username(self) -> None:
        first_status, _ = await self.client.post(
            "/auth/signup",
            json_body={
                "email": "dup@example.com",
                "username": "first",
                "password": "mypassword123",
            },
        )
        self.assertEqual(first_status, 201)

        email_status, email_payload = await self.client.post(
            "/auth/signup",
            json_body={
                "email": "dup@example.com",
                "username": "second",
                "password": "mypassword123",
            },
        )
        self.assertEqual(email_status, 400)
        self.assertEqual(email_payload["detail"], "Email already registered")

        username_status, username_payload = await self.client.post(
            "/auth/signup",
            json_body={
                "email": "other@example.com",
                "username": "first",
                "password": "mypassword123",
            },
        )
        self.assertEqual(username_status, 400)
        self.assertEqual(username_payload["detail"], "Username already registered")

    async def test_login_returns_bearer_token_for_valid_credentials(self) -> None:
        signup_status, signup_payload = await self.client.post(
            "/auth/signup",
            json_body={
                "email": "login@example.com",
                "username": "login-user",
                "password": "mypassword123",
            },
        )
        self.assertEqual(signup_status, 201)

        status_code, payload = await self.client.post(
            "/auth/login",
            data={
                "username": "login@example.com",
                "password": "mypassword123",
            },
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["token_type"], "bearer")
        token_payload = decode_access_token(payload["access_token"])
        self.assertEqual(token_payload["sub"], signup_payload["id"])
        refresh_payload = decode_refresh_token(payload["refresh_token"])
        self.assertEqual(refresh_payload["sub"], signup_payload["id"])

    async def test_refresh_returns_new_token_pair_for_valid_refresh_token(self) -> None:
        signup_status, _ = await self.client.post(
            "/auth/signup",
            json_body={
                "email": "refresh@example.com",
                "username": "refresh-user",
                "password": "mypassword123",
            },
        )
        self.assertEqual(signup_status, 201)

        login_status, login_payload = await self.client.post(
            "/auth/login",
            data={
                "username": "refresh@example.com",
                "password": "mypassword123",
            },
        )
        self.assertEqual(login_status, 200)
        first_refresh = login_payload["refresh_token"]

        refresh_status, refresh_payload = await self.client.post(
            "/auth/refresh",
            json_body={"refresh_token": first_refresh},
        )
        self.assertEqual(refresh_status, 200)
        self.assertIn("access_token", refresh_payload)
        self.assertIn("refresh_token", refresh_payload)
        self.assertNotEqual(refresh_payload["refresh_token"], first_refresh)

    async def test_refresh_rejects_invalid_refresh_token(self) -> None:
        status_code, payload = await self.client.post(
            "/auth/refresh",
            json_body={"refresh_token": "not-a-valid-token"},
        )
        self.assertEqual(status_code, 401)
        self.assertIn("detail", payload)

    async def test_login_rejects_invalid_credentials(self) -> None:
        await self.client.post(
            "/auth/signup",
            json_body={
                "email": "badlogin@example.com",
                "username": "badlogin-user",
                "password": "mypassword123",
            },
        )

        wrong_password_status, wrong_password_payload = await self.client.post(
            "/auth/login",
            data={
                "username": "badlogin@example.com",
                "password": "wrong-password",
            },
        )
        self.assertEqual(wrong_password_status, 401)
        self.assertEqual(wrong_password_payload["detail"], "Invalid email or password")

        missing_user_status, missing_user_payload = await self.client.post(
            "/auth/login",
            data={
                "username": "missing@example.com",
                "password": "mypassword123",
            },
        )
        self.assertEqual(missing_user_status, 401)
        self.assertEqual(missing_user_payload["detail"], "Invalid email or password")

    async def test_me_returns_current_user_from_bearer_token(self) -> None:
        await self.client.post(
            "/auth/signup",
            json_body={
                "email": "me@example.com",
                "username": "me-user",
                "password": "mypassword123",
            },
        )
        login_status, login_payload = await self.client.post(
            "/auth/login",
            data={
                "username": "me@example.com",
                "password": "mypassword123",
            },
        )
        self.assertEqual(login_status, 200)

        status_code, payload = await self.client.get(
            "/auth/me",
            headers={"authorization": f"Bearer {login_payload['access_token']}"},
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["email"], "me@example.com")
        self.assertEqual(payload["username"], "me-user")
        self.assertNotIn("hashed_password", payload)

    async def test_me_requires_valid_bearer_token(self) -> None:
        status_code, payload = await self.client.get("/auth/me")
        self.assertEqual(status_code, 401)
        self.assertEqual(payload["detail"], "Invalid authentication credentials")

        invalid_status, invalid_payload = await self.client.get(
            "/auth/me",
            headers={"authorization": "Bearer not-a-real-token"},
        )
        self.assertEqual(invalid_status, 401)
        self.assertEqual(invalid_payload["detail"], "Invalid authentication credentials")
