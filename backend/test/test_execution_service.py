from __future__ import annotations

import unittest

from app.services.execution_service import ExecutionService


class ExecutionServiceStartNodeTests(unittest.TestCase):
    def test_resolve_start_node_accepts_requested_root_trigger(self) -> None:
        definition = {
            "nodes": [
                {"id": "manual_a", "type": "manual_trigger"},
                {"id": "manual_b", "type": "manual_trigger"},
                {"id": "task_1", "type": "filter"},
                {"id": "task_2", "type": "filter"},
            ],
            "edges": [
                {"id": "e1", "source": "manual_a", "target": "task_1"},
                {"id": "e2", "source": "manual_b", "target": "task_2"},
            ],
        }

        start_node_id = ExecutionService._resolve_start_node_id(
            definition=definition,
            expected_types={"manual_trigger"},
            preferred_node_id="manual_b",
        )

        self.assertEqual(start_node_id, "manual_b")

    def test_resolve_start_node_rejects_requested_non_root_trigger(self) -> None:
        definition = {
            "nodes": [
                {"id": "manual_a", "type": "manual_trigger"},
                {"id": "manual_b", "type": "manual_trigger"},
            ],
            "edges": [
                {"id": "e1", "source": "manual_a", "target": "manual_b"},
            ],
        }

        with self.assertRaisesRegex(ValueError, "root trigger"):
            ExecutionService._resolve_start_node_id(
                definition=definition,
                expected_types={"manual_trigger"},
                preferred_node_id="manual_b",
            )

    def test_resolve_start_node_rejects_type_mismatch(self) -> None:
        definition = {
            "nodes": [
                {"id": "manual_start", "type": "manual_trigger"},
                {"id": "form_start", "type": "form_trigger"},
            ],
            "edges": [],
        }

        with self.assertRaisesRegex(ValueError, "must be one of"):
            ExecutionService._resolve_start_node_id(
                definition=definition,
                expected_types={"manual_trigger"},
                preferred_node_id="form_start",
            )

    def test_resolve_start_node_accepts_schedule_trigger(self) -> None:
        definition = {
            "nodes": [
                {"id": "schedule_start", "type": "schedule_trigger"},
                {"id": "task_1", "type": "filter"},
            ],
            "edges": [
                {"id": "e1", "source": "schedule_start", "target": "task_1"},
            ],
        }

        start_node_id = ExecutionService._resolve_start_node_id(
            definition=definition,
            expected_types={"schedule_trigger"},
            preferred_node_id="schedule_start",
        )

        self.assertEqual(start_node_id, "schedule_start")


class ExecutionServiceLoopMetadataTests(unittest.TestCase):
    def test_build_effective_loop_settings_uses_workflow_defaults_when_no_override(self) -> None:
        metadata = ExecutionService._build_effective_loop_settings_metadata(
            workflow_definition={
                "loop_control": {
                    "enabled": True,
                    "max_node_executions": 5,
                    "max_total_node_executions": 20,
                }
            },
            loop_control_override=None,
        )

        self.assertEqual(
            metadata,
            {
                "enabled": True,
                "max_node_executions": 5,
                "max_total_node_executions": 20,
                "source": "workflow_definition",
                "workflow_default": {
                    "enabled": True,
                    "max_node_executions": 5,
                    "max_total_node_executions": 20,
                },
                "runtime_override": None,
            },
        )

    def test_build_effective_loop_settings_applies_runtime_override(self) -> None:
        metadata = ExecutionService._build_effective_loop_settings_metadata(
            workflow_definition={
                "loop_control": {
                    "enabled": True,
                    "max_node_executions": 3,
                    "max_total_node_executions": 30,
                }
            },
            loop_control_override={
                "enabled": True,
                "max_node_executions": 7,
                "max_total_node_executions": 70,
            },
        )

        self.assertEqual(metadata["enabled"], True)
        self.assertEqual(metadata["max_node_executions"], 7)
        self.assertEqual(metadata["max_total_node_executions"], 70)
        self.assertEqual(metadata["source"], "runtime_override")
        self.assertEqual(
            metadata["workflow_default"],
            {
                "enabled": True,
                "max_node_executions": 3,
                "max_total_node_executions": 30,
            },
        )
        self.assertEqual(
            metadata["runtime_override"],
            {
                "enabled": True,
                "max_node_executions": 7,
                "max_total_node_executions": 70,
            },
        )


if __name__ == "__main__":
    unittest.main()
