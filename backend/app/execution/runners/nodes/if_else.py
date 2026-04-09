from typing import Any
from app.execution.utils import evaluate_condition, get_nested_value


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
        field_value = get_nested_value(input_data, field, runner_name="IfElseRunner")

        # --- Step 4: Evaluate condition ---
        result = evaluate_condition(field_value, operator, value)

        # --- Step 5: Return original data + _branch ---
        return {
            **input_data,
            "_branch": "true" if result else "false"
        }
