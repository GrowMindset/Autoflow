from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit


class ASGITestClient:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        parsed = urlsplit(path)
        body = b""
        request_headers = []

        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers.append((b"content-type", b"application/json"))
        elif data is not None:
            from urllib.parse import urlencode
            body = urlencode(data).encode("utf-8")
            request_headers.append((b"content-type", b"application/x-www-form-urlencoded"))

        for key, value in (headers or {}).items():
            request_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))

        response_status: int | None = None
        response_headers: list[tuple[bytes, bytes]] = []
        response_body = bytearray()
        body_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_status, response_headers
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": parsed.path,
            "raw_path": parsed.path.encode("ascii"),
            "query_string": parsed.query.encode("ascii"),
            "headers": request_headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
        }
        await self.app(scope, receive, send)

        decoded_headers = {
            key.decode("latin-1"): value.decode("latin-1") for key, value in response_headers
        }
        return int(response_status or 500), decoded_headers, bytes(response_body)

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
