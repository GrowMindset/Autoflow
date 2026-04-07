from typing import Any, Dict, List

from app.execution.runners.if_else import get_nested_value


class SplitInRunner:
    """
    Emits each item from the configured array as a separate child execution context.

    Config shape:
    {
        "input_key": "tickets"
    }

    Output shape:
    [
        {"item": {...}, "_split_index": 0},
        {"item": {...}, "_split_index": 1}
    ]
    """

    def run(self, config: dict, input_data: dict) -> list:
        input_key = config.get("input_key")
        if not input_key:
            raise ValueError("SplitInRunner: 'input_key' is missing in config")

        items = get_nested_value(input_data, input_key)
        if not isinstance(items, list):
            raise ValueError(
                f"SplitInRunner: '{input_key}' must be a list, got {type(items).__name__}"
            )

        return [
            {"item": item, "_split_index": index}
            for index, item in enumerate(items)
        ]


# Testing
# runner = SplitInRunner()
# result = runner.run(
#     config={"input_key": "tickets"},
#     input_data={"tickets": [{"id": 1}, {"id": 2}]}
# )
# print(result)
# # → [{"item": {"id": 1}, "_split_index": 0}, {"item": {"id": 2}, "_split_index": 1}]
