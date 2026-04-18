"""Shared helpers for local file read/write workflow nodes."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ALLOWED_EXTENSIONS = {
    "txt",
    "md",
    "json",
    "jsonl",
    "csv",
    "tsv",
    "log",
    "xml",
    "html",
    "htm",
    "yml",
    "yaml",
    "ini",
    "cfg",
    "conf",
    "sql",
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "css",
    "scss",
    "svg",
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "bmp",
    "zip",
    "gz",
    "tar",
    "docx",
    "xlsx",
    "pptx",
}

TEXT_EXTENSIONS = {
    "txt",
    "md",
    "json",
    "jsonl",
    "csv",
    "tsv",
    "log",
    "xml",
    "html",
    "htm",
    "yml",
    "yaml",
    "ini",
    "cfg",
    "conf",
    "sql",
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "css",
    "scss",
    "svg",
}


def _split_env_list(raw_value: str, *, separator: str) -> list[str]:
    return [item.strip() for item in raw_value.split(separator) if item.strip()]


def get_allowed_extensions() -> set[str]:
    raw = str(os.getenv("FILE_NODE_ALLOWED_EXTENSIONS") or "").strip()
    if not raw:
        return set(DEFAULT_ALLOWED_EXTENSIONS)
    return {item.lower().lstrip(".") for item in _split_env_list(raw, separator=",")}


def get_allowed_base_dirs() -> list[Path]:
    raw = str(os.getenv("FILE_NODE_ALLOWED_BASE_DIRS") or "").strip()
    if raw:
        candidates = _split_env_list(raw, separator=os.pathsep)
    else:
        candidates = [os.getcwd(), "/tmp"]

    resolved: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = Path(os.getcwd()) / path
        normalized = path.resolve(strict=False)
        token = str(normalized)
        if token in seen:
            continue
        seen.add(token)
        resolved.append(normalized)
    return resolved


def resolve_local_file_path(raw_path: str) -> Path:
    path_text = str(raw_path or "").strip()
    if not path_text:
        raise ValueError("File node: 'file_path' is required.")

    expanded = Path(os.path.expandvars(path_text)).expanduser()
    if not expanded.is_absolute():
        expanded = Path(os.getcwd()) / expanded
    resolved = expanded.resolve(strict=False)
    _assert_path_allowed(resolved)
    _assert_extension_allowed(resolved)
    return resolved


def _assert_path_allowed(target: Path) -> None:
    allowed_dirs = get_allowed_base_dirs()
    target_text = str(target)
    for base_dir in allowed_dirs:
        base_text = str(base_dir)
        try:
            if os.path.commonpath([target_text, base_text]) == base_text:
                return
        except ValueError:
            continue
    allowed_label = ", ".join(str(item) for item in allowed_dirs)
    raise ValueError(
        f"File node: access denied for path '{target}'. Allowed base directories: {allowed_label}"
    )


def _assert_extension_allowed(path: Path) -> None:
    extension = path.suffix.lower().lstrip(".")
    if not extension:
        return
    allowed_extensions = get_allowed_extensions()
    if extension in allowed_extensions:
        return
    sample = ", ".join(sorted(allowed_extensions)[:20])
    raise ValueError(
        f"File node: extension '.{extension}' is not allowed. Allowed extensions include: {sample}"
    )


def parse_max_bytes(raw_value: object) -> int:
    default_limit = int(str(os.getenv("FILE_NODE_MAX_BYTES") or "5242880"))
    value = raw_value if raw_value not in (None, "") else default_limit
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except Exception as exc:
        raise ValueError("File node: max_bytes must be an integer.") from exc
    if parsed <= 0:
        raise ValueError("File node: max_bytes must be > 0.")
    return min(parsed, 50 * 1024 * 1024)

