"""File Write node runner for writing local files."""

from __future__ import annotations

import base64
import json
from typing import Any

from app.execution.runners.nodes.file_node_utils import resolve_local_file_path
from app.execution.utils import get_nested_value


class FileWriteRunner:
    _SUPPORTED_WRITE_MODES = {"create", "overwrite", "append"}
    _SUPPORTED_CONTENT_SOURCES = {"input", "config"}
    _SUPPORTED_INPUT_FORMATS = {"auto", "text", "json", "base64"}

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        file_path = resolve_local_file_path(str(config.get("file_path") or ""))
        write_mode = str(config.get("write_mode") or "create").strip().lower()
        if write_mode not in self._SUPPORTED_WRITE_MODES:
            raise ValueError("File Write: write_mode must be create, overwrite, or append.")

        content_source = str(config.get("content_source") or "input").strip().lower()
        if content_source not in self._SUPPORTED_CONTENT_SOURCES:
            raise ValueError("File Write: content_source must be input or config.")

        input_format = str(config.get("input_format") or "auto").strip().lower()
        if input_format not in self._SUPPORTED_INPUT_FORMATS:
            raise ValueError("File Write: input_format must be auto, text, json, or base64.")

        encoding = str(config.get("encoding") or "utf-8").strip() or "utf-8"
        create_dirs = self._parse_bool(config.get("create_dirs"), default=True)

        source_value = self._resolve_source_value(
            config=config,
            input_data=input_data,
            content_source=content_source,
        )
        payload, payload_kind = self._prepare_payload(
            value=source_value,
            input_format=input_format,
        )

        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        elif not file_path.parent.exists():
            raise ValueError(
                f"File Write: parent directory does not exist for '{file_path}'."
            )

        existed_before = file_path.exists()
        bytes_written = self._write_payload(
            file_path=str(file_path),
            payload=payload,
            payload_kind=payload_kind,
            write_mode=write_mode,
            encoding=encoding,
        )

        output: dict[str, Any] = dict(input_data) if isinstance(input_data, dict) else {}
        output["file_write"] = {
            "path": str(file_path),
            "bytes_written": bytes_written,
            "write_mode": write_mode,
            "content_source": content_source,
            "input_format": input_format,
            "created_new_file": not existed_before,
        }
        output["file_path"] = str(file_path)
        return output

    def _resolve_source_value(
        self,
        *,
        config: dict[str, Any],
        input_data: Any,
        content_source: str,
    ) -> Any:
        if content_source == "config":
            return config.get("content_text", "")

        input_key = str(config.get("input_key") or "").strip()
        if input_key:
            if not isinstance(input_data, dict):
                raise ValueError(
                    "File Write: input_key is set but input_data is not an object."
                )
            return get_nested_value(input_data, input_key, runner_name="FileWriteRunner")
        return input_data

    @staticmethod
    def _prepare_payload(*, value: Any, input_format: str) -> tuple[str | bytes, str]:
        if input_format == "base64":
            if not isinstance(value, str):
                raise ValueError("File Write: base64 input_format requires a string value.")
            try:
                return base64.b64decode(value.encode("ascii")), "binary"
            except Exception as exc:
                raise ValueError("File Write: invalid base64 content.") from exc

        if input_format == "json":
            return json.dumps(value, ensure_ascii=False, indent=2), "text"

        if input_format == "text":
            return "" if value is None else str(value), "text"

        # auto
        if isinstance(value, (bytes, bytearray)):
            return bytes(value), "binary"
        if isinstance(value, str):
            return value, "text"
        return json.dumps(value, ensure_ascii=False, indent=2), "text"

    @staticmethod
    def _write_payload(
        *,
        file_path: str,
        payload: str | bytes,
        payload_kind: str,
        write_mode: str,
        encoding: str,
    ) -> int:
        if payload_kind == "binary":
            mode = {
                "create": "xb",
                "overwrite": "wb",
                "append": "ab",
            }[write_mode]
            try:
                with open(file_path, mode) as handle:
                    return handle.write(payload if isinstance(payload, bytes) else payload.encode(encoding))
            except FileExistsError as exc:
                raise ValueError(
                    f"File Write: file already exists at '{file_path}' and write_mode='create'."
                ) from exc

        mode = {
            "create": "x",
            "overwrite": "w",
            "append": "a",
        }[write_mode]
        text_payload = payload if isinstance(payload, str) else payload.decode(encoding, errors="replace")
        try:
            with open(file_path, mode, encoding=encoding) as handle:
                written = handle.write(text_payload)
                return len(text_payload.encode(encoding)) if isinstance(written, int) else len(
                    text_payload.encode(encoding)
                )
        except FileExistsError as exc:
            raise ValueError(
                f"File Write: file already exists at '{file_path}' and write_mode='create'."
            ) from exc

    @staticmethod
    def _parse_bool(value: Any, *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

