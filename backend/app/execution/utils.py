from typing import Any


def evaluate_condition(field_value: Any, operator: str, compare_value: str) -> bool:
    """
    Evaluate a single condition.
    Converts types smartly before comparing.
    """

    # Try to convert compare_value to number if field_value is a number
    if isinstance(field_value, (int, float)):
        try:
            compare_value = type(field_value)(compare_value)
        except (ValueError, TypeError):
            pass

    match operator:
        case "equals":
            return str(field_value) == str(compare_value)
        case "not_equals":
            return str(field_value) != str(compare_value)
        case "greater_than":
            return float(field_value) > float(compare_value)
        case "less_than":
            return float(field_value) < float(compare_value)
        case "contains":
            return str(compare_value) in str(field_value)
        case "not_contains":
            return str(compare_value) not in str(field_value)
        case _:
            raise ValueError(f"Unknown operator: {operator}")


def get_nested_value(data: dict, field_path: str, runner_name: str = "Runner") -> Any:
    """
    Supports dot notation for nested fields.
    
    Example:
        get_nested_value({"user": {"status": "paid"}}, "user.status")
        → "paid"
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
