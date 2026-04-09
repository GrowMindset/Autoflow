from typing import Any, Dict, List

from app.execution.utils import get_nested_value


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

        items = get_nested_value(input_data, input_key, runner_name="SplitInRunner")
        if not isinstance(items, list):
            raise ValueError(
                f"SplitInRunner: '{input_key}' must be a list, got {type(items).__name__}"
            )

        return [
            {"item": item, "_split_index": index}
            for index, item in enumerate(items)
        ]
