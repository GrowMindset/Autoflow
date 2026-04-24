"""HTTP Request runner (n8n-style) with method + auth support."""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import socket
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlparse

import httpx


class HttpRequestRunner:
    _SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
    _SUPPORTED_AUTH_MODES = {"none", "bearer", "basic", "api_key"}
    _SUPPORTED_BODY_TYPES = {"none", "json", "form", "raw"}
    _SUPPORTED_API_KEY_IN = {"header", "query"}
    _LOCAL_HOST_NAMES = {"localhost", "localhost.localdomain"}
    _HOST_RESOLVER_CONTEXT_KEY = "outbound_host_resolver"

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}

        method = str(config.get("method") or "GET").strip().upper()
        if method not in self._SUPPORTED_METHODS:
            raise ValueError(
                f"HTTP Request: Unsupported method '{method}'. "
                f"Use one of: {', '.join(sorted(self._SUPPORTED_METHODS))}."
            )

        url = str(config.get("url") or "").strip()
        if not url:
            raise ValueError("HTTP Request: 'url' is required.")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("HTTP Request: 'url' must start with http:// or https://.")
        outbound_resolver = self._extract_outbound_resolver(context)
        self._validate_outbound_target(url, resolver=outbound_resolver)

        headers = self._parse_mapping(config.get("headers_json"), field_name="headers_json")
        query = self._parse_mapping(config.get("query_json"), field_name="query_json")
        timeout_seconds = self._parse_timeout(config.get("timeout_seconds"))
        follow_redirects = self._parse_bool(config.get("follow_redirects"), default=True)
        continue_on_fail = self._parse_bool(config.get("continue_on_fail"), default=False)
        response_format = str(config.get("response_format") or "auto").strip().lower()
        if response_format not in {"auto", "json", "text"}:
            raise ValueError("HTTP Request: response_format must be one of auto, json, text.")

        auth = self._apply_auth(
            config=config,
            headers=headers,
            query=query,
            context=context,
        )

        body_type = str(config.get("body_type") or "none").strip().lower()
        if body_type not in self._SUPPORTED_BODY_TYPES:
            raise ValueError(
                "HTTP Request: body_type must be one of none, json, form, raw."
            )

        request_kwargs: dict[str, Any] = {}
        if body_type == "json":
            request_kwargs["json"] = self._parse_json_value(
                config.get("body_json"),
                field_name="body_json",
                default={},
            )
        elif body_type == "form":
            request_kwargs["data"] = self._parse_mapping(
                config.get("body_form_json"),
                field_name="body_form_json",
            )
        elif body_type == "raw":
            request_kwargs["content"] = str(config.get("body_raw") or "")

        response = self._perform_request(
            method=method,
            url=url,
            headers=headers,
            query=query,
            auth=auth,
            timeout_seconds=timeout_seconds,
            follow_redirects=follow_redirects,
            request_kwargs=request_kwargs,
            outbound_resolver=outbound_resolver,
        )

        parsed_body, body_kind = self._parse_response_body(
            response=response,
            response_format=response_format,
        )

        if response.status_code >= 400 and not continue_on_fail:
            message = (
                f"HTTP Request: {response.status_code} {response.reason_phrase or ''}".strip()
            )
            if isinstance(parsed_body, str) and parsed_body.strip():
                short = parsed_body.strip()
                if len(short) > 300:
                    short = f"{short[:297]}..."
                message = f"{message} - {short}"
            raise ValueError(message)

        output: dict[str, Any] = {}
        if isinstance(input_data, dict):
            output.update(input_data)

        output["http_response"] = {
            "ok": response.is_success,
            "status_code": response.status_code,
            "reason": response.reason_phrase,
            "url": str(response.request.url),
            "method": method,
            "headers": dict(response.headers),
            "body_kind": body_kind,
            "body": parsed_body,
        }
        output["status_code"] = response.status_code
        output["response_body"] = parsed_body
        output["response_headers"] = dict(response.headers)
        return output

    @staticmethod
    def _parse_bool_env(value: str | None, *, default: bool) -> bool:
        if value is None:
            return default
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    @classmethod
    def _private_networks_allowed(cls) -> bool:
        return cls._parse_bool_env(
            os.getenv("HTTP_REQUEST_ALLOW_PRIVATE_NETWORKS"),
            default=False,
        )

    @staticmethod
    def _explicit_allowed_hosts() -> set[str]:
        raw = str(os.getenv("HTTP_REQUEST_ALLOWED_HOSTS") or "")
        hosts = {item.strip().lower() for item in raw.split(",") if item.strip()}
        return hosts

    @classmethod
    def _extract_outbound_resolver(
        cls,
        context: dict[str, Any],
    ) -> Callable[[str, int], Iterable[str]] | None:
        candidate = context.get(cls._HOST_RESOLVER_CONTEXT_KEY)
        if candidate is None:
            return None
        if not callable(candidate):
            raise ValueError(
                "HTTP Request: outbound_host_resolver must be callable when provided in context."
            )
        return candidate

    @classmethod
    def _validate_outbound_target(
        cls,
        url: str,
        *,
        resolver: Callable[[str, int], Iterable[str]] | None = None,
    ) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            raise ValueError("HTTP Request: URL host is missing.")
        host_lower = host.strip().lower()

        if host_lower in cls._explicit_allowed_hosts():
            return
        if cls._private_networks_allowed():
            return

        if host_lower in cls._LOCAL_HOST_NAMES or host_lower.endswith(".localhost"):
            raise ValueError(
                "HTTP Request: outbound requests to localhost/private networks are blocked."
            )

        ip_literal = cls._parse_ip_literal(host_lower)
        if ip_literal is not None:
            cls._ensure_public_ip(ip_literal)
            return

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        resolved_ips = cls._resolve_host_addresses(
            host=host_lower,
            port=port,
            resolver=resolver,
        )
        for resolved_ip in resolved_ips:
            cls._ensure_public_ip(resolved_ip)

    @classmethod
    def _resolve_host_addresses(
        cls,
        *,
        host: str,
        port: int,
        resolver: Callable[[str, int], Iterable[str]] | None,
    ) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        if resolver is not None:
            try:
                resolved_items = list(resolver(host, port))
            except Exception as exc:
                raise ValueError(f"HTTP Request: could not resolve host '{host}'.") from exc
            if not resolved_items:
                raise ValueError(f"HTTP Request: could not resolve host '{host}'.")
            resolved_ips = [
                cls._parse_ip_literal(str(item))
                for item in resolved_items
            ]
            filtered = [item for item in resolved_ips if item is not None]
            if not filtered:
                raise ValueError(f"HTTP Request: could not resolve host '{host}'.")
            return filtered

        try:
            resolved = socket.getaddrinfo(
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ValueError(f"HTTP Request: could not resolve host '{host}'.") from exc

        if not resolved:
            raise ValueError(f"HTTP Request: could not resolve host '{host}'.")

        resolved_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for item in resolved:
            sockaddr = item[4]
            if not sockaddr:
                continue
            resolved_ip = cls._parse_ip_literal(str(sockaddr[0]))
            if resolved_ip is None:
                continue
            resolved_ips.append(resolved_ip)

        if not resolved_ips:
            raise ValueError(f"HTTP Request: could not resolve host '{host}'.")
        return resolved_ips

    @staticmethod
    def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        cleaned = host.strip().strip("[]")
        try:
            return ipaddress.ip_address(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _ensure_public_ip(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if ip_obj.version == 6 and ip_obj.ipv4_mapped is not None:
            ip_obj = ip_obj.ipv4_mapped
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
            or (hasattr(ip_obj, "is_site_local") and getattr(ip_obj, "is_site_local"))
        ):
            raise ValueError(
                "HTTP Request: outbound requests to localhost/private networks are blocked."
            )

    @staticmethod
    def _parse_bool(raw_value: Any, *, default: bool) -> bool:
        if raw_value is None:
            return default
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, (int, float)):
            return bool(raw_value)
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _parse_timeout(raw_timeout: Any) -> float:
        if raw_timeout in (None, ""):
            return 30.0
        try:
            timeout = float(raw_timeout)
        except Exception as exc:
            raise ValueError("HTTP Request: timeout_seconds must be a number.") from exc
        if timeout <= 0:
            raise ValueError("HTTP Request: timeout_seconds must be greater than 0.")
        return min(timeout, 300.0)

    @staticmethod
    def _parse_mapping(raw_value: Any, *, field_name: str) -> dict[str, Any]:
        if raw_value is None:
            return {}
        if isinstance(raw_value, dict):
            return {str(k): v for k, v in raw_value.items()}
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except Exception as exc:
                raise ValueError(f"HTTP Request: {field_name} must be valid JSON object.") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"HTTP Request: {field_name} must be a JSON object.")
            return {str(k): v for k, v in parsed.items()}
        raise ValueError(f"HTTP Request: {field_name} must be an object or JSON string.")

    @staticmethod
    def _parse_json_value(raw_value: Any, *, field_name: str, default: Any) -> Any:
        if raw_value is None:
            return default
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return default
            try:
                return json.loads(text)
            except Exception as exc:
                raise ValueError(f"HTTP Request: {field_name} must be valid JSON.") from exc
        return raw_value

    def _apply_auth(
        self,
        *,
        config: dict[str, Any],
        headers: dict[str, Any],
        query: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[str, str] | None:
        auth_mode = str(config.get("auth_mode") or "none").strip().lower()
        if auth_mode not in self._SUPPORTED_AUTH_MODES:
            raise ValueError(
                "HTTP Request: auth_mode must be one of none, bearer, basic, api_key."
            )
        if auth_mode == "none":
            return None

        credential_data = self._resolve_credential_data(config=config, context=context)

        if auth_mode == "bearer":
            token = self._first_non_empty(
                config.get("bearer_token"),
                credential_data.get("bearer_token"),
                credential_data.get("access_token"),
                credential_data.get("api_key"),
            )
            if not token:
                raise ValueError(
                    "HTTP Request: bearer auth selected but token is missing."
                )
            prefix = str(config.get("bearer_prefix") or "Bearer").strip()
            headers["Authorization"] = f"{prefix} {token}".strip() if prefix else str(token)
            return None

        if auth_mode == "basic":
            username = self._first_non_empty(
                config.get("username"),
                credential_data.get("username"),
                credential_data.get("user_email"),
            )
            password = self._first_non_empty(
                config.get("password"),
                credential_data.get("password"),
                credential_data.get("app_password"),
                credential_data.get("api_key"),
            )
            if not username or not password:
                raise ValueError(
                    "HTTP Request: basic auth selected but username/password are missing."
                )
            return (str(username), str(password))

        # api_key
        key_name = str(
            config.get("api_key_name")
            or credential_data.get("api_key_name")
            or "x-api-key"
        ).strip()
        key_value = self._first_non_empty(
            config.get("api_key_value"),
            credential_data.get("api_key"),
            credential_data.get("access_token"),
        )
        if not key_value:
            raise ValueError(
                "HTTP Request: api_key auth selected but api key value is missing."
            )
        location = str(config.get("api_key_in") or "header").strip().lower()
        if location not in self._SUPPORTED_API_KEY_IN:
            raise ValueError("HTTP Request: api_key_in must be 'header' or 'query'.")
        if location == "query":
            query[key_name] = str(key_value)
        else:
            prefix = str(config.get("api_key_prefix") or "").strip()
            headers[key_name] = f"{prefix} {key_value}".strip() if prefix else str(key_value)
        return None

    @staticmethod
    def _first_non_empty(*values: Any) -> str | None:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _resolve_credential_data(
        *,
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        credential_id = config.get("credential_id")
        if not credential_id:
            return {}
        resolved: dict[str, dict[str, Any]] = (
            context.get("resolved_credential_data") or {}
        )
        value = resolved.get(str(credential_id))
        return value if isinstance(value, dict) else {}

    def _perform_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, Any],
        query: dict[str, Any],
        auth: tuple[str, str] | None,
        timeout_seconds: float,
        follow_redirects: bool,
        request_kwargs: dict[str, Any],
        outbound_resolver: Callable[[str, int], Iterable[str]] | None,
    ) -> httpx.Response:
        try:
            with httpx.Client(
                timeout=timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=query,
                    auth=auth,
                    **request_kwargs,
                )
                if not follow_redirects:
                    return response

                redirect_count = 0
                max_redirects = 10
                while response.is_redirect:
                    redirect_count += 1
                    if redirect_count > max_redirects:
                        raise ValueError(
                            f"HTTP Request: too many redirects (>{max_redirects})."
                        )
                    next_request = response.next_request
                    if next_request is None:
                        break
                    self._validate_outbound_target(
                        str(next_request.url),
                        resolver=outbound_resolver,
                    )
                    response = client.send(next_request)
                return response
        except httpx.TimeoutException as exc:
            raise ValueError("HTTP Request: request timed out.") from exc
        except httpx.RequestError as exc:
            raise ValueError(f"HTTP Request: network error - {exc}") from exc

    @staticmethod
    def _is_textual_content_type(content_type: str) -> bool:
        lowered = content_type.lower()
        if lowered.startswith("text/"):
            return True
        return any(
            token in lowered
            for token in (
                "application/xml",
                "application/javascript",
                "application/x-www-form-urlencoded",
                "application/xhtml+xml",
            )
        )

    def _parse_response_body(
        self,
        *,
        response: httpx.Response,
        response_format: str,
    ) -> tuple[Any, str]:
        content_type = str(response.headers.get("content-type") or "").lower()

        if response_format == "json":
            try:
                return response.json(), "json"
            except Exception:
                return response.text, "text"

        if response_format == "text":
            return response.text, "text"

        # auto
        if "application/json" in content_type:
            try:
                return response.json(), "json"
            except Exception:
                return response.text, "text"

        if self._is_textual_content_type(content_type):
            return response.text, "text"

        encoded = base64.b64encode(response.content).decode("ascii")
        return encoded, "base64"
