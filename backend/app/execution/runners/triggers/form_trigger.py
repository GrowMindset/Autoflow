from app.schemas.form_fields import validate_form_submission


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

    def run(self, config: dict, input_data: dict | None, context: dict | None = None, **kwargs) -> dict:
        if input_data is None:
            raw_payload = {}
        elif isinstance(input_data, dict):
            raw_payload = dict(input_data)
        else:
            raise ValueError(
                "FormTriggerRunner: input_data must be a dict or None"
            )

        payload = validate_form_submission(config.get("fields"), raw_payload)

        return {
            "triggered": True,
            "trigger_type": "form",
            **payload,
        }
