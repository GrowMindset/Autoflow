import json
import math
import re
from datetime import datetime
from typing import Any, Dict, List

from app.execution.utils import evaluate_condition, get_nested_value


def set_nested_value(data: Dict[str, Any], field_path: str, value: Any) -> Dict[str, Any]:
    keys = field_path.split(".")
    result = dict(data)
    current = result

    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            raise ValueError(
                f"FilterRunner: Cannot set '{field_path}' because '{key}' is missing or not a dict"
            )
        current[key] = dict(current[key])
        current = current[key]

    current[keys[-1]] = value
    return result


class FilterRunner:
    """
    Filters an array field using a condition and returns the same input_data
    with the filtered array replacing the original.

    Config shape:
    {
        "input_key": "items",
        "field": "amount",
        "operator": "greater_than",
        "value": "500"
    }

    Output shape:
    {
        ...original input_data fields..., 
        "items": [ ...filtered items... ]
    }
    """

    def run(self, config: dict, input_data: dict, context: dict[str, Any] = None) -> dict:
        input_key = config.get("input_key")
        if not input_key:
            raise ValueError("FilterRunner: 'input_key' is missing in config")

        conditions = self._resolve_conditions(config)

        array_value = get_nested_value(input_data, input_key, runner_name="FilterRunner")
        if not isinstance(array_value, list):
            raise ValueError(
                f"FilterRunner: '{input_key}' must be a list, got {type(array_value).__name__}"
            )

        filtered_items: List[Any] = []
        for item in array_value:
            if not isinstance(item, dict):
                raise ValueError(
                    "FilterRunner: Each element in the input list must be a dict"
                )

            should_include = self._evaluate_item_condition(item, conditions[0])
            for idx in range(1, len(conditions)):
                join_with_previous = conditions[idx]["join_with_previous"]
                if join_with_previous == "and" and not should_include:
                    continue
                if join_with_previous == "or" and should_include:
                    continue

                current_result = self._evaluate_item_condition(item, conditions[idx])
                if join_with_previous == "or":
                    should_include = should_include or current_result
                else:
                    should_include = should_include and current_result

            if should_include:
                filtered_items.append(item)

        return set_nested_value(input_data, input_key, filtered_items)

    def _resolve_conditions(self, config: dict) -> list[dict[str, Any]]:
        fallback_join = str(
            config.get("logic")
            or config.get("condition_logic")
            or config.get("combine")
            or "and"
        ).strip().lower()
        if fallback_join not in {"and", "or"}:
            raise ValueError("FilterRunner: 'logic' must be 'and' or 'or'")

        raw_conditions = config.get("conditions")
        if isinstance(raw_conditions, list) and len(raw_conditions) > 0:
            return [
                self._normalize_condition(item, idx, fallback_join=fallback_join)
                for idx, item in enumerate(raw_conditions)
            ]

        # Legacy single-condition compatibility.
        legacy_condition = {
            "field": config.get("field"),
            "operator": config.get("operator"),
            "value": config.get("value"),
            "data_type": config.get("data_type"),
            "value_mode": config.get("value_mode"),
            "value_field": config.get("value_field"),
            "case_sensitive": config.get("case_sensitive"),
        }
        return [self._normalize_condition(legacy_condition, 0, fallback_join=fallback_join)]

    @staticmethod
    def _normalize_condition(
        raw_condition: Any,
        index: int,
        *,
        fallback_join: str,
    ) -> dict[str, Any]:
        if not isinstance(raw_condition, dict):
            raise ValueError(f"FilterRunner: conditions[{index}] must be an object")

        field = raw_condition.get("field")
        operator = raw_condition.get("operator")
        data_type_raw = str(raw_condition.get("data_type") or "").strip().lower()
        data_type = data_type_raw if data_type_raw in {
            "string",
            "number",
            "boolean",
            "date",
            "array",
            "object",
        } else ""
        value_mode = str(raw_condition.get("value_mode") or "literal").strip().lower()
        value_field = raw_condition.get("value_field")
        case_sensitive = FilterRunner._to_bool(raw_condition.get("case_sensitive"), default=True)
        join_raw = str(
            raw_condition.get("join_with_previous")
            or raw_condition.get("condition")
            or raw_condition.get("logic")
            or fallback_join
        ).strip().lower()
        join_with_previous = "or" if join_raw == "or" else "and"

        if not field:
            raise ValueError(f"FilterRunner: conditions[{index}] is missing 'field'")
        if not operator:
            raise ValueError(f"FilterRunner: conditions[{index}] is missing 'operator'")
        if value_mode not in {"literal", "field"}:
            raise ValueError(
                f"FilterRunner: conditions[{index}] 'value_mode' must be 'literal' or 'field'"
            )
        operator_key = str(operator).strip().lower()
        operators_without_compare = {
            "exists",
            "does_not_exist",
            "not_exists",
            "is_empty",
            "is_not_empty",
            "is_true",
            "is_false",
        }
        if operator_key in operators_without_compare:
            value_mode = "literal"
            value_field = ""
            compare_value = None
        elif value_mode == "field":
            if not value_field:
                raise ValueError(
                    f"FilterRunner: conditions[{index}] requires 'value_field' when value_mode='field'"
                )
            compare_value = None
        else:
            compare_value = raw_condition.get("value")
            if compare_value is None:
                raise ValueError(
                    f"FilterRunner: conditions[{index}] is missing 'value'"
                )

        return {
            "field": field,
            "operator": operator,
            "data_type": data_type,
            "value_mode": value_mode,
            "value_field": value_field,
            "value": compare_value,
            "case_sensitive": case_sensitive,
            "join_with_previous": "and" if index == 0 else join_with_previous,
        }

    def _evaluate_item_condition(self, item: dict[str, Any], condition: dict[str, Any]) -> bool:
        field = str(condition.get("field") or "").strip()
        operator = str(condition.get("operator") or "").strip().lower()
        data_type = str(condition.get("data_type") or "").strip().lower()
        value_mode = str(condition.get("value_mode") or "literal").strip().lower()
        case_sensitive = bool(condition.get("case_sensitive", True))

        left_exists, field_value = self._try_get_nested_value(item, field)

        if operator == "exists":
            return left_exists
        if operator in {"does_not_exist", "not_exists"}:
            return not left_exists
        if operator == "is_empty":
            return left_exists and self._is_empty(field_value)
        if operator == "is_not_empty":
            return left_exists and not self._is_empty(field_value)

        if not left_exists:
            raise ValueError(f"FilterRunner: Field '{field}' not found in input item")

        if operator == "is_true":
            return self._coerce_bool(field_value, context_label=f"field '{field}'")
        if operator == "is_false":
            return not self._coerce_bool(field_value, context_label=f"field '{field}'")

        if value_mode == "field":
            value_field = str(condition.get("value_field") or "").strip()
            if not value_field:
                raise ValueError("FilterRunner: 'value_field' is required when value_mode='field'")
            compare_exists, compare_value = self._try_get_nested_value(item, value_field)
            if not compare_exists:
                raise ValueError(
                    f"FilterRunner: Field '{value_field}' not found in input item"
                )
        else:
            compare_value = condition.get("value")

        return self._evaluate_with_data_type(
            left_value=field_value,
            compare_value=compare_value,
            operator=operator,
            data_type=data_type,
            case_sensitive=case_sensitive,
        )

    @staticmethod
    def _try_get_nested_value(data: dict[str, Any], field_path: str) -> tuple[bool, Any]:
        keys = [key for key in str(field_path or "").split(".") if key != ""]
        if not keys:
            return False, None

        current: Any = data
        for key in keys:
            if not isinstance(current, dict):
                return False, None
            if key not in current:
                return False, None
            current = current[key]
        return True, current

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value == ""
        if isinstance(value, (list, tuple, dict, set)):
            return len(value) == 0
        return False

    def _evaluate_with_data_type(
        self,
        *,
        left_value: Any,
        compare_value: Any,
        operator: str,
        data_type: str,
        case_sensitive: bool,
    ) -> bool:
        normalized_operator = operator.strip().lower()

        if data_type == "string":
            return self._evaluate_string(
                left_value,
                compare_value,
                normalized_operator,
                case_sensitive=case_sensitive,
            )
        if data_type == "number":
            return self._evaluate_number(left_value, compare_value, normalized_operator)
        if data_type == "boolean":
            return self._evaluate_boolean(left_value, compare_value, normalized_operator)
        if data_type == "date":
            return self._evaluate_date(left_value, compare_value, normalized_operator)
        if data_type == "array":
            return self._evaluate_array(left_value, compare_value, normalized_operator)
        if data_type == "object":
            return self._evaluate_object(left_value, compare_value, normalized_operator)

        # Backward-compatible fallback when data_type is omitted.
        if normalized_operator in {"starts_with", "does_not_start_with"}:
            left = "" if left_value is None else str(left_value)
            right = "" if compare_value is None else str(compare_value)
            if not case_sensitive:
                left = left.lower()
                right = right.lower()
            return left.startswith(right) if normalized_operator == "starts_with" else not left.startswith(right)
        if normalized_operator in {"ends_with", "does_not_end_with"}:
            left = "" if left_value is None else str(left_value)
            right = "" if compare_value is None else str(compare_value)
            if not case_sensitive:
                left = left.lower()
                right = right.lower()
            return left.endswith(right) if normalized_operator == "ends_with" else not left.endswith(right)
        if normalized_operator in {"matches_regex", "does_not_match_regex"}:
            left = "" if left_value is None else str(left_value)
            pattern = "" if compare_value is None else str(compare_value)
            matched = re.search(pattern, left) is not None
            return matched if normalized_operator == "matches_regex" else not matched
        if normalized_operator in {"greater_than_or_equals", "greater_than_or_equal"}:
            return float(left_value) >= float(compare_value)
        if normalized_operator in {"less_than_or_equals", "less_than_or_equal"}:
            return float(left_value) <= float(compare_value)

        return evaluate_condition(
            left_value,
            normalized_operator,
            compare_value,
            case_sensitive=case_sensitive,
        )

    def _evaluate_string(
        self,
        left_value: Any,
        compare_value: Any,
        operator: str,
        *,
        case_sensitive: bool,
    ) -> bool:
        left = "" if left_value is None else str(left_value)
        right = "" if compare_value is None else str(compare_value)

        if not case_sensitive:
            left = left.lower()
            right = right.lower()

        if operator == "equals":
            return left == right
        if operator == "not_equals":
            return left != right
        if operator == "contains":
            return right in left
        if operator == "not_contains":
            return right not in left
        if operator == "starts_with":
            return left.startswith(right)
        if operator in {"does_not_start_with", "not_starts_with"}:
            return not left.startswith(right)
        if operator == "ends_with":
            return left.endswith(right)
        if operator in {"does_not_end_with", "not_ends_with"}:
            return not left.endswith(right)
        if operator == "matches_regex":
            return re.search(right, left) is not None
        if operator in {"does_not_match_regex", "not_matches_regex"}:
            return re.search(right, left) is None
        raise ValueError(f"Unknown string operator: {operator}")

    def _evaluate_number(self, left_value: Any, compare_value: Any, operator: str) -> bool:
        left = self._coerce_number(left_value, context_label="left number value")
        right = self._coerce_number(compare_value, context_label="right number value")

        if operator == "equals":
            return left == right
        if operator == "not_equals":
            return left != right
        if operator == "greater_than":
            return left > right
        if operator == "less_than":
            return left < right
        if operator in {"greater_than_or_equals", "greater_than_or_equal"}:
            return left >= right
        if operator in {"less_than_or_equals", "less_than_or_equal"}:
            return left <= right
        raise ValueError(f"Unknown number operator: {operator}")

    def _evaluate_boolean(self, left_value: Any, compare_value: Any, operator: str) -> bool:
        left = self._coerce_bool(left_value, context_label="left boolean value")
        if operator == "is_true":
            return left
        if operator == "is_false":
            return not left

        right = self._coerce_bool(compare_value, context_label="right boolean value")
        if operator == "equals":
            return left == right
        if operator == "not_equals":
            return left != right
        raise ValueError(f"Unknown boolean operator: {operator}")

    def _evaluate_date(self, left_value: Any, compare_value: Any, operator: str) -> bool:
        left = self._coerce_datetime(left_value, context_label="left date value")
        right = self._coerce_datetime(compare_value, context_label="right date value")

        if operator == "equals":
            return left == right
        if operator == "not_equals":
            return left != right
        if operator in {"after", "is_after"}:
            return left > right
        if operator in {"before", "is_before"}:
            return left < right
        if operator in {"after_or_equal", "is_after_or_equal"}:
            return left >= right
        if operator in {"before_or_equal", "is_before_or_equal"}:
            return left <= right
        raise ValueError(f"Unknown date operator: {operator}")

    def _evaluate_array(self, left_value: Any, compare_value: Any, operator: str) -> bool:
        if not isinstance(left_value, list):
            raise ValueError(
                f"FilterRunner: expected array value, got {type(left_value).__name__}"
            )

        compare_candidate = self._parse_json_literal(compare_value)
        if operator == "contains":
            return compare_candidate in left_value
        if operator == "not_contains":
            return compare_candidate not in left_value

        length = len(left_value)
        target = self._coerce_number(compare_candidate, context_label="array length compare value")
        if not math.isfinite(target):
            raise ValueError("FilterRunner: array length comparison value must be finite")
        target_int = int(target)
        if target != target_int:
            raise ValueError("FilterRunner: array length comparison value must be an integer")

        if operator == "length_equals":
            return length == target_int
        if operator == "length_not_equals":
            return length != target_int
        if operator == "length_greater_than":
            return length > target_int
        if operator == "length_less_than":
            return length < target_int
        if operator == "length_greater_than_or_equals":
            return length >= target_int
        if operator == "length_less_than_or_equals":
            return length <= target_int
        raise ValueError(f"Unknown array operator: {operator}")

    def _evaluate_object(self, left_value: Any, compare_value: Any, operator: str) -> bool:
        if not isinstance(left_value, dict):
            raise ValueError(
                f"FilterRunner: expected object value, got {type(left_value).__name__}"
            )

        if operator == "equals":
            return left_value == self._coerce_object(compare_value, context_label="right object value")
        if operator == "not_equals":
            return left_value != self._coerce_object(compare_value, context_label="right object value")
        raise ValueError(f"Unknown object operator: {operator}")

    @staticmethod
    def _coerce_number(value: Any, *, context_label: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"FilterRunner: {context_label} cannot be boolean")
        try:
            number = float(value)
        except Exception as exc:
            raise ValueError(f"FilterRunner: {context_label} is not a number") from exc
        if not math.isfinite(number):
            raise ValueError(f"FilterRunner: {context_label} must be finite")
        return number

    @staticmethod
    def _coerce_bool(value: Any, *, context_label: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value in (0, 1):
                return bool(value)
            raise ValueError(f"FilterRunner: {context_label} numeric value must be 0 or 1")
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise ValueError(f"FilterRunner: {context_label} is not a boolean")

    @staticmethod
    def _coerce_datetime(value: Any, *, context_label: str) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value))
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError(f"FilterRunner: {context_label} is empty")
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                return datetime.fromisoformat(text)
            except Exception as exc:
                raise ValueError(
                    f"FilterRunner: {context_label} is not a valid ISO date/time"
                ) from exc
        raise ValueError(f"FilterRunner: {context_label} is not a valid date/time")

    @staticmethod
    def _coerce_object(value: Any, *, context_label: str) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception as exc:
                raise ValueError(f"FilterRunner: {context_label} is not valid JSON object") from exc
            if isinstance(parsed, dict):
                return parsed
        raise ValueError(f"FilterRunner: {context_label} is not an object")

    @staticmethod
    def _parse_json_literal(value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if text == "":
                return value
            try:
                return json.loads(text)
            except Exception:
                return value
        return value

    @staticmethod
    def _to_bool(raw_value: Any, *, default: bool) -> bool:
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


# Testing
# runner = FilterRunner()
# result = runner.run(
#     config={"input_key": "items", "field": "amount", "operator": "greater_than", "value": "500"},
#     input_data={"items": [{"amount": 300}, {"amount": 700}, {"amount": 150}], "customer": "A"}
# )
# print(result)
# # → {"items": [{"amount": 700}], "customer": "A"}

# result = runner.run(
#     config={"input_key": "items", "field": "status", "operator": "equals", "value": "ok"},
#     input_data={"items": [{"status": "ok"}, {"status": "fail"}]}
# )
# print(result)
# # → {"items": [{"status": "ok"}]}
