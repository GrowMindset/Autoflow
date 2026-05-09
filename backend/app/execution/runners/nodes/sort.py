from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.execution.utils import get_nested_value


def set_nested_value(data: dict[str, Any], field_path: str, value: Any) -> dict[str, Any]:
    keys = field_path.split(".")
    result = dict(data)
    current = result

    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            raise ValueError(
                f"SortRunner: Cannot set '{field_path}' because '{key}' is missing or not a dict"
            )
        current[key] = dict(current[key])
        current = current[key]

    current[keys[-1]] = value
    return result


class SortRunner:
    """
    Sorts an input array and returns the same payload with the array replaced.

    Config shape:
    {
        "input_key": "items",
        "sort_by": "amount",      # optional, for object arrays
        "order": "asc",           # asc | desc
        "data_type": "auto",      # auto | string | number | boolean | date
        "nulls": "last",          # first | last
        "case_sensitive": false   # used for string sorting
    }
    """

    _SUPPORTED_ORDER = {"asc", "desc"}
    _SUPPORTED_DATA_TYPES = {"auto", "string", "number", "boolean", "date"}
    _SUPPORTED_NULLS = {"first", "last"}

    def run(
        self,
        config: dict[str, Any],
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        input_key = str(config.get("input_key") or "").strip()
        if not input_key:
            raise ValueError("SortRunner: 'input_key' is missing in config")

        sort_by = str(config.get("sort_by") or "").strip()
        order = str(config.get("order") or "asc").strip().lower()
        data_type = str(config.get("data_type") or "auto").strip().lower()
        nulls = str(config.get("nulls") or "last").strip().lower()
        case_sensitive = self._parse_bool(config.get("case_sensitive"), default=False)

        if order not in self._SUPPORTED_ORDER:
            raise ValueError("SortRunner: 'order' must be 'asc' or 'desc'")
        if data_type not in self._SUPPORTED_DATA_TYPES:
            raise ValueError(
                "SortRunner: 'data_type' must be one of auto, string, number, boolean, date"
            )
        if nulls not in self._SUPPORTED_NULLS:
            raise ValueError("SortRunner: 'nulls' must be 'first' or 'last'")

        items = get_nested_value(input_data, input_key, runner_name="SortRunner")
        if not isinstance(items, list):
            raise ValueError(
                f"SortRunner: '{input_key}' must be a list, got {type(items).__name__}"
            )

        sortable: list[tuple[tuple[int, Any], Any]] = []
        null_items: list[tuple[int, Any]] = []

        for index, item in enumerate(items):
            raw_value = self._extract_sort_value(item=item, sort_by=sort_by)
            normalized = self._normalize_value(
                value=raw_value,
                data_type=data_type,
                case_sensitive=case_sensitive,
            )
            if normalized is None:
                null_items.append((index, item))
                continue
            sortable.append((normalized, item))

        # Keep sorting stable so equal keys preserve input order.
        sortable.sort(key=lambda entry: entry[0], reverse=(order == "desc"))

        sorted_items = [entry[1] for entry in sortable]
        null_payloads = [entry[1] for entry in null_items]

        if nulls == "first":
            final_items = [*null_payloads, *sorted_items]
        else:
            final_items = [*sorted_items, *null_payloads]

        return set_nested_value(input_data, input_key, final_items)

    @staticmethod
    def _extract_sort_value(*, item: Any, sort_by: str) -> Any:
        if not sort_by:
            return item
        if not isinstance(item, dict):
            raise ValueError(
                "SortRunner: 'sort_by' requires each array item to be an object."
            )
        try:
            return get_nested_value(item, sort_by, runner_name="SortRunner")
        except Exception:
            return None

    def _normalize_value(
        self,
        *,
        value: Any,
        data_type: str,
        case_sensitive: bool,
    ) -> tuple[int, Any] | None:
        if value is None:
            return None

        if data_type == "auto":
            return self._normalize_auto(value=value, case_sensitive=case_sensitive)
        if data_type == "string":
            text = str(value)
            return (3, text if case_sensitive else text.lower())
        if data_type == "number":
            try:
                return (0, float(value))
            except Exception as exc:
                raise ValueError(
                    f"SortRunner: value '{value}' cannot be parsed as number."
                ) from exc
        if data_type == "boolean":
            return (2, 1 if self._parse_bool(value, default=False) else 0)
        if data_type == "date":
            parsed = self._parse_datetime(value)
            if parsed is None:
                raise ValueError(
                    f"SortRunner: value '{value}' cannot be parsed as date."
                )
            return (1, parsed.timestamp())
        return (3, str(value))

    def _normalize_auto(
        self,
        *,
        value: Any,
        case_sensitive: bool,
    ) -> tuple[int, Any]:
        if isinstance(value, bool):
            return (2, 1 if value else 0)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return (0, float(value))
        if isinstance(value, datetime):
            return (1, value.timestamp())
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                try:
                    return (0, float(candidate))
                except Exception:
                    pass
                parsed = self._parse_datetime(candidate)
                if parsed is not None:
                    return (1, parsed.timestamp())
            return (3, value if case_sensitive else value.lower())
        if isinstance(value, (dict, list)):
            return (3, json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
        return (3, str(value))

    @staticmethod
    def _parse_bool(raw_value: Any, *, default: bool) -> bool:
        if raw_value is None:
            return default
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, (int, float)):
            return raw_value != 0
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value))
            except Exception:
                return None
        if not isinstance(value, str):
            return None

        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            return None
