from typing import Any, Dict, List

from app.execution.utils import get_nested_value


class AggregateRunner:
    """
    Aggregates items from a list and returns a single scalar result.

    Config shape:
    {
        "input_key": "items",
        "field": "amount",
        "operation": "sum",
        "output_key": "total_revenue"
    }

    Output shape:
    {
        "total_revenue": 1150
    }
    """

    VALID_OPERATIONS = {"sum", "count", "min", "max", "avg"}

    def run(self, config: dict, input_data: dict) -> dict:
        input_key = config.get("input_key")
        operation = config.get("operation")
        output_key = config.get("output_key", "result")
        field = config.get("field")

        if not input_key:
            raise ValueError("AggregateRunner: 'input_key' is missing in config")
        if not operation:
            raise ValueError("AggregateRunner: 'operation' is missing in config")
        if operation not in self.VALID_OPERATIONS:
            raise ValueError(
                f"AggregateRunner: Unsupported operation '{operation}'"
            )
        if operation != "count" and not field:
            raise ValueError(
                f"AggregateRunner: 'field' is required for operation '{operation}'"
            )

        items = get_nested_value(input_data, input_key, runner_name="AggregateRunner")
        if not isinstance(items, list):
            raise ValueError(
                f"AggregateRunner: '{input_key}' must be a list, got {type(items).__name__}"
            )

        if operation == "count":
            return {output_key: len(items)}

        values: List[float] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("AggregateRunner: Each list item must be a dict")

            value = get_nested_value(item, field, runner_name="AggregateRunner")
            try:
                number = float(value)
            except (ValueError, TypeError):
                raise ValueError(
                    f"AggregateRunner: Field '{field}' value must be numeric, got {value!r}"
                )
            values.append(number)

        if not values:
            if operation == "sum":
                result = 0
            else:
                raise ValueError(
                    f"AggregateRunner: Cannot compute '{operation}' on empty list"
                )
        elif operation == "sum":
            result = sum(values)
        elif operation == "min":
            result = min(values)
        elif operation == "max":
            result = max(values)
        else:
            result = sum(values) / len(values)

        return {output_key: result}
