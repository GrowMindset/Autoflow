from typing import Any, Dict
from dateutil import parser

from app.execution.utils import get_nested_value


def set_nested_value(data: Dict[str, Any], field_path: str, value: Any) -> Dict[str, Any]:
    keys = field_path.split(".")
    result = dict(data)
    current = result

    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            raise ValueError(
                f"DateTimeFormatRunner: Cannot set '{field_path}' because '{key}' is missing or not a dict"
            )
        current[key] = dict(current[key])
        current = current[key]

    current[keys[-1]] = value
    return result


class DateTimeFormatRunner:
    """
    Parses a date string and overwrites the same field with a formatted result.

    Config shape:
    {
        "field": "order_date",
        "output_format": "%d %B %Y"
    }

    Output shape:
    {
        ...original input_data fields..., 
        "order_date": "07 April 2026"
    }
    """

    def run(self, config: dict, input_data: dict, context: dict[str, Any] = None) -> dict:
        field = config.get("field")
        output_format = config.get("output_format")

        if not field:
            raise ValueError("DateTimeFormatRunner: 'field' is missing in config")
        if not output_format:
            raise ValueError("DateTimeFormatRunner: 'output_format' is missing in config")

        field_value = get_nested_value(input_data, field, runner_name="DateTimeFormatRunner")
        if field_value is None:
            raise ValueError(
                f"DateTimeFormatRunner: Field '{field}' is None and cannot be parsed"
            )

        try:
            parsed = parser.parse(str(field_value))
        except Exception as exc:
            raise ValueError(
                f"DateTimeFormatRunner: Could not parse '{field_value}' as a date: {exc}"
            ) from exc

        formatted = parsed.strftime(output_format)
        return set_nested_value(input_data, field, formatted)


# Testing
# runner = DateTimeFormatRunner()
# result = runner.run(
#     config={"field": "order_date", "output_format": "%d %B %Y"},
#     input_data={"order_date": "2026-04-07", "amount": 500}
# )
# print(result)
# # → {"order_date": "07 April 2026", "amount": 500}

# result = runner.run(
#     config={"field": "order_date", "output_format": "%I:%M %p"},
#     input_data={"order_date": "2026-04-07T14:30:00Z"}
# )
# print(result)
# # → {"order_date": "02:30 PM"}
