from __future__ import annotations

import json
from typing import Any


class WorkflowTriggerRunner:
    """
    Defines the entry point for a child workflow called by execute_workflow.
    """

    def run(
        self,
        config: dict[str, Any],
        input_data: dict[str, Any] | None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if input_data is None:
            payload: dict[str, Any] = {}
        elif isinstance(input_data, dict):
            payload = dict(input_data)
        else:
            raise ValueError(
                "WorkflowTriggerRunner: input_data must be a dict or None"
            )

        input_data_mode = str(config.get("input_data_mode") or "accept_all").strip()
        if input_data_mode == "fields":
            return self._validate_fields(config=config, payload=payload)

        if input_data_mode == "json_example":
            return self._validate_json_example(config=config, payload=payload)

        return payload

    @classmethod
    def _validate_fields(
        cls,
        *,
        config: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        raw_schema = config.get("input_schema")
        if raw_schema is None:
            raw_schema = []
        if not isinstance(raw_schema, list):
            raise ValueError("WorkflowTriggerRunner: input_schema must be a list")

        validated: dict[str, Any] = {}
        for field in raw_schema:
            if not isinstance(field, dict):
                continue
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            if name not in payload:
                raise ValueError(
                    f"WorkflowTriggerRunner: required field '{name}' is missing"
                )
            validated[name] = cls._coerce_value(
                payload[name],
                str(field.get("type") or "any").strip().lower(),
                field_name=name,
            )
        return validated

    @staticmethod
    def _validate_json_example(
        *,
        config: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        raw_example = str(config.get("json_example") or "").strip()
        if not raw_example:
            return dict(payload)
        try:
            parsed = json.loads(raw_example)
        except Exception as exc:
            raise ValueError("WorkflowTriggerRunner: json_example must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("WorkflowTriggerRunner: json_example must be a JSON object")

        expected = set(parsed.keys())
        received = set(payload.keys())
        validated = {
            key: payload[key]
            for key in parsed.keys()
            if key in payload
        }
        if expected and expected != received:
            validated["_warnings"] = [
                "Workflow input keys differ from the configured JSON example."
            ]
        return validated

    @staticmethod
    def _coerce_value(value: Any, value_type: str, *, field_name: str) -> Any:
        if value_type in {"", "any", "allow any type"}:
            return value
        if value_type == "string":
            return value if isinstance(value, str) else str(value)
        if value_type == "number":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value
            try:
                number = float(str(value).strip())
            except Exception as exc:
                raise ValueError(
                    f"WorkflowTriggerRunner: field '{field_name}' must be a number"
                ) from exc
            return int(number) if number.is_integer() else number
        if value_type == "boolean":
            if isinstance(value, bool):
                return value
            normalized = str(value).strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
            raise ValueError(
                f"WorkflowTriggerRunner: field '{field_name}' must be a boolean"
            )
        if value_type == "array":
            if isinstance(value, list):
                return value
            raise ValueError(
                f"WorkflowTriggerRunner: field '{field_name}' must be an array"
            )
        if value_type == "object":
            if isinstance(value, dict):
                return value
            raise ValueError(
                f"WorkflowTriggerRunner: field '{field_name}' must be an object"
            )
        return value
