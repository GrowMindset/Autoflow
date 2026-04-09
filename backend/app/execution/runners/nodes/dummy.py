from __future__ import annotations

from typing import Any


class DummyNodeRunner:
    """Pass-through runner for frontend-only or not-yet-implemented nodes."""

    def __init__(self, node_type: str) -> None:
        self.node_type = node_type

    def run(self, config: dict[str, Any], input_data: Any) -> dict[str, Any]:
        payload = dict(input_data) if isinstance(input_data, dict) else {}

        return {
            **payload,
            "dummy_node_executed": True,
            "dummy_node_type": self.node_type,
            "dummy_node_message": f"Dummy node executed for '{self.node_type}'",
        }
