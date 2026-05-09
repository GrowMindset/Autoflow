from __future__ import annotations

from typing import Any

from app.execution.utils import get_nested_value


def set_nested_value(data: dict[str, Any], field_path: str, value: Any) -> dict[str, Any]:
    keys = field_path.split(".")
    result = dict(data)
    current = result

    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            raise ValueError(
                f"LimitRunner: Cannot set '{field_path}' because '{key}' is missing or not a dict"
            )
        current[key] = dict(current[key])
        current = current[key]

    current[keys[-1]] = value
    return result


class LimitRunner:
    """
    Limits items in an input array and returns the same payload with the array replaced.

    Config shape:
    {
        "input_key": "items",
        "limit": 10,
        "offset": 0,
        "start_from": "start"  # start | end
    }
    """

    def run(
        self,
        config: dict[str, Any],
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        input_key = str(config.get("input_key") or "").strip()
        if not input_key:
            raise ValueError("LimitRunner: 'input_key' is missing in config")

        limit = self._parse_int(config.get("limit"), default=10, field_name="limit")
        offset = self._parse_int(config.get("offset"), default=0, field_name="offset")
        start_from = str(config.get("start_from") or "start").strip().lower()

        if limit < 0:
            raise ValueError("LimitRunner: 'limit' must be >= 0")
        if offset < 0:
            raise ValueError("LimitRunner: 'offset' must be >= 0")
        if start_from not in {"start", "end"}:
            raise ValueError("LimitRunner: 'start_from' must be 'start' or 'end'")

        items = get_nested_value(input_data, input_key, runner_name="LimitRunner")
        if not isinstance(items, list):
            raise ValueError(
                f"LimitRunner: '{input_key}' must be a list, got {type(items).__name__}"
            )

        if limit <= 0:
            sliced = []
        elif start_from == "end":
            end_index = max(0, len(items) - offset)
            start_index = max(0, end_index - limit)
            sliced = items[start_index:end_index]
        else:
            sliced = items[offset: offset + limit]
        return set_nested_value(input_data, input_key, sliced)

    @staticmethod
    def _parse_int(raw_value: Any, *, default: int, field_name: str) -> int:
        if raw_value in (None, ""):
            return default
        try:
            return int(str(raw_value).strip())
        except Exception as exc:
            raise ValueError(f"LimitRunner: '{field_name}' must be an integer") from exc
