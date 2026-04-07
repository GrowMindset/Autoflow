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


class IfElseRunner:
    """
    Evaluates a condition on input_data and returns the same data
    with a _branch field ('true' or 'false') added.

    Config shape:
    {
        "field": "status",
        "operator": "equals",
        "value": "paid"
    }

    Output shape:
    {
        ...original input_data fields...,
        "_branch": "true"   ← or "false"
    }
    """

    def run(self, config: dict, input_data: dict) -> dict:
        # --- Step 1: Read config ---
        field    = config.get("field")
        operator = config.get("operator")
        value    = config.get("value")

        # --- Step 2: Validate config ---
        if not field:
            raise ValueError("IfElseRunner: 'field' is missing in config")
        if not operator:
            raise ValueError("IfElseRunner: 'operator' is missing in config")
        if value is None:
            raise ValueError("IfElseRunner: 'value' is missing in config")

        # --- Step 3: Get field value from input_data ---
        # Supports dot notation: "user.status" → input_data["user"]["status"]
        field_value = get_nested_value(input_data, field)

        # --- Step 4: Evaluate condition ---
        result = evaluate_condition(field_value, operator, value)

        # --- Step 5: Return original data + _branch ---
        return {
            **input_data,
            "_branch": "true" if result else "false"
        }


def get_nested_value(data: dict, field_path: str) -> Any:
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
                f"IfElseRunner: Cannot access '{key}' — "
                f"'{field_path}' does not exist in input data"
            )
        if key not in current:
            raise ValueError(
                f"IfElseRunner: Field '{field_path}' not found in input data"
            )
        current = current[key]

    return current

# Testing
# runner = IfElseRunner()

# # Test 1 — true branch
# result = runner.run(
#     config={"field": "status", "operator": "equals", "value": "paid"},
#     input_data={"status": "paid", "amount": 500}
# )
# print(result)
# # → {"status": "paid", "amount": 500, "_branch": "true"}

# # Test 2 — false branch
# result = runner.run(
#     config={"field": "status", "operator": "equals", "value": "paid"},
#     input_data={"status": "failed", "amount": 500}
# )
# # → {"status": "failed", "amount": 500, "_branch": "false"}
# print(result)

# # Test 3 — nested field (dot notation)
# result = runner.run(
#     config={"field": "payment.status", "operator": "equals", "value": "paid"},
#     input_data={"payment": {"status": "paid"}, "amount": 500}
# )
# print(result)
# # → {"payment": {"status": "paid"}, "amount": 500, "_branch": "true"}
