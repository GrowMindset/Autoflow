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


if __name__ == "__main__":
    unittest.main()
