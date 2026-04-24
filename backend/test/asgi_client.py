from __future__ import annotations

import json
from typing import Any

import httpx


class ASGITestClient:
    """Small async wrapper around httpx.AsyncClient for ASGI app tests.

    Why this exists:
    - Uses real ASGI transport behavior (no synthetic early disconnect events).
    - Manages FastAPI lifespan so startup/shutdown hooks run deterministically.
    - Preserves legacy helper API used by existing unittest-based tests.
    """

    def __init__(
        self,
        app: Any,
        *,
        base_url: str = "http://testserver",
        request_timeout_seconds: float = 20.0,
    ) -> None:
        self.app = app
        self.base_url = base_url
        self.request_timeout_seconds = request_timeout_seconds
        self._client: httpx.AsyncClient | None = None
        self._lifespan_cm: Any | None = None

    async def __aenter__(self) -> "ASGITestClient":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def _ensure_client(self) -> None:
        if self._client is not None:
            return

        # Explicit lifespan management keeps app startup/shutdown deterministic.
        self._lifespan_cm = self.app.router.lifespan_context(self.app)
        await self._lifespan_cm.__aenter__()

        transport = httpx.ASGITransport(
            app=self.app,
            raise_app_exceptions=True,
            client=("testclient", 50000),
        )
        self._client = httpx.AsyncClient(
            transport=transport,
            base_url=self.base_url,
            follow_redirects=False,
            timeout=self.request_timeout_seconds,
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

        if self._lifespan_cm is not None:
            await self._lifespan_cm.__aexit__(None, None, None)
            self._lifespan_cm = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        await self._ensure_client()
        assert self._client is not None  # Narrow type for static analyzers.

        request_kwargs: dict[str, Any] = {
            "method": method.upper(),
            "url": path,
            "headers": headers or {},
            "timeout": self.request_timeout_seconds,
        }
        if json_body is not None:
            request_kwargs["json"] = json_body
        elif data is not None:
            request_kwargs["data"] = data

        response = await self._client.request(**request_kwargs)
        return response.status_code, dict(response.headers), response.content

    async def get(self, path: str, *, headers: dict[str, str] | None = None) -> tuple[int, Any]:
        return await self._json_request("GET", path, headers=headers)

    async def post(
        self,
        path: str,
        *,
        json_body: Any | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        return await self._json_request("POST", path, json_body=json_body, data=data, headers=headers)

    async def put(
        self,
        path: str,
        *,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        return await self._json_request("PUT", path, json_body=json_body, headers=headers)

    async def delete(
        self, path: str, *, headers: dict[str, str] | None = None
    ) -> tuple[int, Any]:
        return await self._json_request("DELETE", path, headers=headers)

    async def _json_request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        status_code, response_headers, body = await self.request(
            method, path, json_body=json_body, data=data, headers=headers
        )
        content_type = response_headers.get("content-type", "")
        if "application/json" in content_type and body:
            return status_code, json.loads(body)
        return status_code, body.decode("utf-8")
