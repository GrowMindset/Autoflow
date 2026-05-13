from typing import Any

from app.execution.utils import evaluate_condition as evaluate_operator_condition
from app.execution.utils import get_nested_value


CONDITION_TYPE_VALUES = {"AND", "OR"}
OPERATORS_WITHOUT_COMPARE_VALUE = set()


def normalize_condition_config(config: dict[str, Any], *, runner_name: str = "ConditionEvaluator") -> dict[str, Any]:
    safe_config = dict(config or {})
    condition_type = str(safe_config.get("condition_type") or "AND").strip().upper()
    if condition_type not in CONDITION_TYPE_VALUES:
        raise ValueError(f"{runner_name}: 'condition_type' must be 'AND' or 'OR'")

    raw_conditions = safe_config.get("conditions")
    conditions: list[dict[str, Any]] = []
    has_legacy_signal = any(
        [
            str(safe_config.get("field") or "").strip(),
            str(safe_config.get("value_field") or "").strip(),
            "value" in safe_config and str(safe_config.get("value") or "").strip(),
        ]
    )
    if isinstance(raw_conditions, list) and raw_conditions:
        try:
            for index, raw_condition in enumerate(raw_conditions):
                conditions.append(_normalize_condition(raw_condition, index, runner_name=runner_name))
        except ValueError:
            if not has_legacy_signal:
                raise
            conditions = []

    if not conditions:
        legacy_condition = {
            "field": safe_config.get("field"),
            "operator": safe_config.get("operator"),
            "value": safe_config.get("value"),
            "value_mode": safe_config.get("value_mode"),
            "value_field": safe_config.get("value_field"),
            "case_sensitive": safe_config.get("case_sensitive"),
        }
        conditions.append(_normalize_condition(legacy_condition, 0, runner_name=runner_name))

    return {
        "condition_type": condition_type,
        "conditions": conditions,
    }


def evaluate_condition(condition: dict[str, Any], input_data: dict[str, Any]) -> bool:
    normalized = _normalize_condition(condition, 0, runner_name="ConditionEvaluator")
    field_value = get_nested_value(input_data, normalized["field"], runner_name="ConditionEvaluator")

    if normalized["value_mode"] == "field":
        compare_value = get_nested_value(
            input_data,
            normalized["value_field"],
            runner_name="ConditionEvaluator",
        )
    else:
        compare_value = normalized.get("value")

    return evaluate_operator_condition(
        field_value,
        normalized["operator"],
        compare_value,
        case_sensitive=normalized["case_sensitive"],
    )


def evaluate_conditions(
    condition_type: str,
    conditions: list[dict[str, Any]],
    input_data: dict[str, Any],
) -> bool:
    normalized_type = str(condition_type or "AND").strip().upper()
    if normalized_type not in CONDITION_TYPE_VALUES:
        raise ValueError("ConditionEvaluator: 'condition_type' must be 'AND' or 'OR'")
    if not conditions:
        raise ValueError("ConditionEvaluator: at least one condition is required")

    results = [evaluate_condition(condition, input_data) for condition in conditions]
    return all(results) if normalized_type == "AND" else any(results)


def _normalize_condition(raw_condition: Any, index: int, *, runner_name: str) -> dict[str, Any]:
    if not isinstance(raw_condition, dict):
        raise ValueError(f"{runner_name}: conditions[{index}] must be an object")

    field = str(raw_condition.get("field") or "").strip()
    operator = str(raw_condition.get("operator") or "").strip().lower()
    value_mode = str(raw_condition.get("value_mode") or "literal").strip().lower()
    value_field = str(raw_condition.get("value_field") or "").strip()
    case_sensitive = _as_bool(raw_condition.get("case_sensitive"), default=True)

    if not field:
        raise ValueError(f"{runner_name}: conditions[{index}] is missing 'field'")
    if not operator:
        raise ValueError(f"{runner_name}: conditions[{index}] is missing 'operator'")
    if value_mode not in {"literal", "field"}:
        raise ValueError(
            f"{runner_name}: conditions[{index}] 'value_mode' must be 'literal' or 'field'"
        )

    if value_mode == "field":
        if not value_field:
            raise ValueError(
                f"{runner_name}: conditions[{index}] requires 'value_field' when value_mode='field'"
            )
        value = None
    else:
        value = raw_condition.get("value")
        if value is None:
            raise ValueError(f"{runner_name}: conditions[{index}] is missing 'value'")

    return {
        "field": field,
        "operator": operator,
        "value": value,
        "value_mode": value_mode,
        "value_field": value_field,
        "case_sensitive": case_sensitive,
    }


def _as_bool(raw_value: Any, *, default: bool) -> bool:
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
