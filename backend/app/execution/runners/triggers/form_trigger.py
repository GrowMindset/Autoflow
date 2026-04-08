class FormTriggerRunner:
    """
    Emits a form trigger payload for in-memory workflow execution.

    Config shape:
    {
        "fields": [
            {"name": "email", "required": True},
            {"name": "notes", "required": False},
        ]
    }

    Input shape:
    None or {"key": "value"}

    Output shape:
    {
        "triggered": True,
        "trigger_type": "form",
        ...input_data
    }
    """

    def run(self, config: dict, input_data: dict | None) -> dict:
        fields = config.get("fields")
        if not fields or not isinstance(fields, list):
            raise ValueError(
                "FormTriggerRunner: config must have a non-empty 'fields' list"
            )

        for field in fields:
            if not isinstance(field, dict) or not field.get("name"):
                raise ValueError(
                    "FormTriggerRunner: each field definition must include a non-empty 'name'"
                )

        if input_data is None:
            payload = {}
        elif isinstance(input_data, dict):
            payload = dict(input_data)
        else:
            raise ValueError(
                "FormTriggerRunner: input_data must be a dict or None"
            )

        for field in fields:
            if field.get("required") and field["name"] not in payload:
                raise ValueError(
                    f"FormTriggerRunner: required field '{field['name']}' "
                    f"is missing from form submission"
                )

        return {
            "triggered": True,
            "trigger_type": "form",
            **payload,
        }
