from __future__ import annotations

from typing import Any


class ScheduleTriggerRunner:
    """
    Emits a schedule trigger payload for in-memory workflow execution.

    Config shape:
    {
        "timezone": "UTC",
        "enabled": True,
        "rules": [
            {
                "interval": "hours",
                "every": 1,
                "trigger_minute": 0,
                "enabled": True,
            }
        ],
    }

    Input shape:
    None or {"key": "value"}

    Output shape:
    {
        "triggered": True,
        "trigger_type": "schedule",
        ...input_data
    }
    """

    def run(
        self,
        config: dict[str, Any],
        input_data: dict[str, Any] | None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if input_data is None:
            payload: dict[str, Any] = {}
        elif isinstance(input_data, dict):
            payload = dict(input_data)
        else:
            raise ValueError(
                "ScheduleTriggerRunner: input_data must be a dict or None"
            )

        return {
            "triggered": True,
            "trigger_type": "schedule",
            **payload,
        }
