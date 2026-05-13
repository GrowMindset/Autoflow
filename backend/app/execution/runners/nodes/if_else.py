from typing import Any
from app.execution.condition_evaluator import (
    evaluate_conditions,
    normalize_condition_config,
)


class IfElseRunner:
    """
    Evaluates one or more conditions on input_data and returns the same data
    with a _branch field ('true' or 'false') added.

    Config shape:
    {
        "condition_type": "AND",
        "conditions": [
            {"field": "status", "operator": "equals", "value": "paid"}
        ]
    }

    Output shape:
    {
        ...original input_data fields...,
        "_branch": "true"   ← or "false"
    }
    """

    def run(self, config: dict, input_data: dict, context: dict[str, Any] = None) -> dict:
        normalized_config = normalize_condition_config(config, runner_name="IfElseRunner")
        result = evaluate_conditions(
            normalized_config["condition_type"],
            normalized_config["conditions"],
            input_data,
        )

        return {
            **input_data,
            "_branch": "true" if result else "false"
        }


# def get_nested_value(data: dict, field_path: str) -> Any:
#     """
#     Supports dot notation for nested fields.
    
#     Example:
#         get_nested_value({"user": {"status": "paid"}}, "user.status")
#         → "paid"
#     """
#     keys = field_path.split(".")
#     current = data

#     for key in keys:
#         if not isinstance(current, dict):
#             raise ValueError(
#                 f"IfElseRunner: Cannot access '{key}' — "
#                 f"'{field_path}' does not exist in input data"
#             )
#         if key not in current:
#             raise ValueError(
#                 f"IfElseRunner: Field '{field_path}' not found in input data"
#             )
#         current = current[key]

#     return current

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
