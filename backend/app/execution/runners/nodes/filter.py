from typing import Any, Dict, List

from backend.app.execution.runners.nodes.if_else import evaluate_condition, get_nested_value


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

    def run(self, config: dict, input_data: dict) -> dict:
        input_key = config.get("input_key")
        field = config.get("field")
        operator = config.get("operator")
        value = config.get("value")

        if not input_key:
            raise ValueError("FilterRunner: 'input_key' is missing in config")
        if not field:
            raise ValueError("FilterRunner: 'field' is missing in config")
        if not operator:
            raise ValueError("FilterRunner: 'operator' is missing in config")
        if value is None:
            raise ValueError("FilterRunner: 'value' is missing in config")

        array_value = get_nested_value(input_data, input_key)
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
            field_value = get_nested_value(item, field)
            if evaluate_condition(field_value, operator, value):
                filtered_items.append(item)

        return set_nested_value(input_data, input_key, filtered_items)


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
