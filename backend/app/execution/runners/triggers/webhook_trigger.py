class WebhookTriggerRunner:
    """
    Emits a webhook trigger payload for in-memory workflow execution.

    Config shape:
    {}

    Input shape:
    None or {"key": "value"}

    Output shape:
    {
        "triggered": True,
        "trigger_type": "webhook",
        ...input_data
    }
    """

    def run(self, config: dict, input_data: dict | None, context: dict | None = None, **kwargs) -> dict:
        if input_data is None:
            payload = {}
        elif isinstance(input_data, dict):
            payload = dict(input_data)
        else:
            raise ValueError(
                "WebhookTriggerRunner: input_data must be a dict or None"
            )

        return {
            "triggered": True,
            "trigger_type": "webhook",
            **payload,
        }
