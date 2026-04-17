import re
from typing import Any

def resolve_mapping(text: str, data: dict, runner_name: str = "Runner") -> str:
    """
    Finds expressions like {{ $json.path.to.field }} and replaces them with 
    the actual value from the input data.
    """
    if not isinstance(text, str):
        return text

    pattern = r"\{\{\s*\$json\.(.*?)\s*\}\}"
    
    def replacer(match):
        path = match.group(1).strip()
        try:
            return str(get_nested_value(data, path, runner_name))
        except Exception:
            return match.group(0)

    return re.sub(pattern, replacer, text)


def evaluate_condition(
    field_value: Any,
    operator: str,
    compare_value: Any,
    *,
    case_sensitive: bool = True,
) -> bool:
    """
    Evaluates a condition by comparing field_value against compare_value using the given operator.
    """

    # Try to convert compare_value to number if field_value is numeric.
    if isinstance(field_value, (int, float)) and isinstance(compare_value, str):
        try:
            compare_value = type(field_value)(compare_value)
        except (ValueError, TypeError):
            pass

    if operator in {"equals", "not_equals", "contains", "not_contains"}:
        left = "" if field_value is None else str(field_value)
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

    match operator:
        case "greater_than":
            return float(field_value) > float(compare_value)
        case "less_than":
            return float(field_value) < float(compare_value)
        case _:
            raise ValueError(f"Unknown operator: {operator}")


def get_nested_value(data: dict, field_path: str, runner_name: str = "Runner") -> Any:
    """
    Supports dot notation for nested fields.
    
    Example:
        get_nested_value({"user": {"status": "paid"}}, "user.status")
        -> "paid"
    """
    keys = field_path.split(".")
    current = data

    for key in keys:
        if not isinstance(current, dict):
            raise ValueError(
                f"{runner_name}: Cannot access '{key}' — "
                f"'{field_path}' does not exist in input data"
            )
        if key not in current:
            raise ValueError(
                f"{runner_name}: Field '{field_path}' not found in input data"
            )
        current = current[key]

    return current
