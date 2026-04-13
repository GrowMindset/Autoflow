from typing import Any
from app.execution.utils import evaluate_condition, get_nested_value


class SwitchRunner:
    """
    Evaluates multiple conditions (cases) on input_data and returns
    the same data with a _branch field set to the matching case label.

    Config shape:
    {
        "field": "country",
        "cases": [
            {"label": "india",   "operator": "equals", "value": "IN"},
            {"label": "usa",     "operator": "equals", "value": "US"},
            {"label": "uk",      "operator": "equals", "value": "UK"}
        ],
        "default_case": "other"
    }

    Output shape:
    {
        ...original input_data fields...,
        "_branch": "india"    ← or "usa" or "uk" or "other" (default)
    }
    """

    def run(self, config: dict, input_data: dict, context: dict[str, Any] = None) -> dict:

        # --- Step 1: Read config ---
        field        = config.get("field")
        cases        = config.get("cases", [])
        default_case = config.get("default_case", "default")

        # --- Step 2: Validate config ---
        if not field:
            raise ValueError("SwitchRunner: 'field' is missing in config")
        if not isinstance(cases, list) or len(cases) == 0:
            raise ValueError("SwitchRunner: 'cases' must be a non-empty list")

        # Validate each case has required fields
        for i, case in enumerate(cases):
            if not case.get("label"):
                raise ValueError(f"SwitchRunner: case[{i}] is missing 'label'")
            if not case.get("operator"):
                raise ValueError(f"SwitchRunner: case[{i}] is missing 'operator'")
            
            if "value" not in case:
                raise ValueError(
                    f"SwitchRunner: case[{i}] (label='{case.get('label')}') "
                    "is missing 'value'."
                )

        # --- Step 3: Get field value from input_data ---
        field_value = get_nested_value(input_data, field, runner_name="SwitchRunner")

        # --- Step 4: Evaluate cases one by one (first match wins) ---
        matched_branch = None

        for case in cases:
            label    = case.get("label")
            operator = case.get("operator")
            value    = case.get("value", "")

            try:
                result = evaluate_condition(field_value, operator, value)
            except ValueError as e:
                raise ValueError(f"SwitchRunner: Error in case '{label}': {e}")

            if result:
                matched_branch = label
                break   # first match wins — stop checking further cases

        # --- Step 5: Fall back to default if no case matched ---
        if matched_branch is None:
            matched_branch = default_case

        # --- Step 6: Return original data + _branch ---
        return {
            **input_data,
            "_branch": matched_branch
        }
        
# Testings
# runner = SwitchRunner()

# # Test 1 — matches first case
# result = runner.run(
#     config={
#         "field": "country",
#         "cases": [
#             {"label": "india", "operator": "equals", "value": "IN"},
#             {"label": "usa",   "operator": "equals", "value": "US"},
#             {"label": "uk",    "operator": "equals", "value": "UK"}
#         ],
#         "default_case": "other"
#     },
#     input_data={"country": "IN", "order_id": "ORD001"}
# )
# print(result)
# # → {"country": "IN", "order_id": "ORD001", "_branch": "india"}


# # Test 2 — no match → falls to default
# result = runner.run(
#     config={
#         "field": "country",
#         "cases": [
#             {"label": "india", "operator": "equals", "value": "IN"},
#             {"label": "usa",   "operator": "equals", "value": "US"},
#         ],
#         "default_case": "other"
#     },
#     input_data={"country": "AU", "order_id": "ORD002"}
# )
# print(result)
# # → {"country": "AU", "order_id": "ORD002", "_branch": "other"}


# # Test 3 — nested field (dot notation)
# result = runner.run(
#     config={
#         "field": "order.country",
#         "cases": [
#             {"label": "india", "operator": "equals", "value": "IN"},
#         ],
#         "default_case": "other"
#     },
#     input_data={"order": {"country": "IN"}, "amount": 999}
# )
# print(result)
# # → {"order": {"country": "IN"}, "amount": 999, "_branch": "india"}
