"""File Read node runner for reading local files."""

from __future__ import annotations

import base64
import csv
import io
import json
from typing import Any

from app.execution.runners.nodes.file_node_utils import (
    TEXT_EXTENSIONS,
    parse_max_bytes,
    resolve_local_file_path,
)


class FileReadRunner:
    _SUPPORTED_PARSE_AS = {"auto", "text", "json", "csv", "lines", "base64"}

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        file_path = resolve_local_file_path(str(config.get("file_path") or ""))
        if not file_path.exists() or not file_path.is_file():
            raise ValueError(f"File Read: file not found at '{file_path}'.")

        max_bytes = parse_max_bytes(config.get("max_bytes"))
        parse_as = str(config.get("parse_as") or "auto").strip().lower()
        if parse_as not in self._SUPPORTED_PARSE_AS:
            raise ValueError(
                "File Read: parse_as must be one of auto, text, json, csv, lines, base64."
            )

        encoding = str(config.get("encoding") or "utf-8").strip() or "utf-8"
        include_metadata = self._parse_bool(config.get("include_metadata"), default=True)
        csv_delimiter = str(config.get("csv_delimiter") or "").strip() or None

        raw_content = file_path.read_bytes()
        if len(raw_content) > max_bytes:
            raise ValueError(
                f"File Read: file size ({len(raw_content)} bytes) exceeds max_bytes ({max_bytes})."
            )

        content, content_type = self._parse_content(
            raw_content=raw_content,
            extension=file_path.suffix.lower().lstrip("."),
            parse_as=parse_as,
            encoding=encoding,
            csv_delimiter=csv_delimiter,
        )

        output: dict[str, Any] = dict(input_data) if isinstance(input_data, dict) else {}
        output["file_content"] = content
        output["file_read"] = {
            "path": str(file_path),
            "name": file_path.name,
            "extension": file_path.suffix.lower().lstrip("."),
            "size_bytes": len(raw_content),
            "content_type": content_type,
        }
        if include_metadata:
            output["file_metadata"] = {
                "path": str(file_path),
                "name": file_path.name,
                "extension": file_path.suffix.lower().lstrip("."),
                "size_bytes": len(raw_content),
                "encoding": encoding,
            }
        return output

    def _parse_content(
        self,
        *,
        raw_content: bytes,
        extension: str,
        parse_as: str,
        encoding: str,
        csv_delimiter: str | None,
    ) -> tuple[Any, str]:
        if parse_as == "base64":
            return base64.b64encode(raw_content).decode("ascii"), "base64"

        if parse_as == "auto":
            if extension == "json":
                parse_as = "json"
            elif extension in {"csv", "tsv"}:
                parse_as = "csv"
            elif extension in TEXT_EXTENSIONS:
                parse_as = "text"
            else:
                return base64.b64encode(raw_content).decode("ascii"), "base64"

        text_content = raw_content.decode(encoding, errors="replace")

        if parse_as == "text":
            return text_content, "text"
        if parse_as == "lines":
            return text_content.splitlines(), "lines"
        if parse_as == "json":
            try:
                return json.loads(text_content), "json"
            except Exception as exc:
                raise ValueError("File Read: JSON parsing failed for file content.") from exc
        if parse_as == "csv":
            delimiter = csv_delimiter
            if not delimiter:
                delimiter = "\t" if extension == "tsv" else ","
            reader = csv.DictReader(io.StringIO(text_content), delimiter=delimiter)
            return list(reader), "csv"

        return text_content, "text"

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

