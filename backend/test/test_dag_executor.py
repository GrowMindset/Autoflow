import unittest

from app.execution.dag_executor import DagExecutor


class DagExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.executor = DagExecutor()

    def test_build_context_calculates_indegree_and_topological_order(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "filter", "config": {
                    "input_key": "items",
                    "field": "amount",
                    "operator": "greater_than",
                    "value": "500",
                }},
                {"id": "n3", "type": "aggregate", "config": {
                    "input_key": "items",
                    "operation": "count",
                }},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        context = self.executor.build_context(definition)

        self.assertEqual(context.indegree, {"n1": 0, "n2": 1, "n3": 1})
        self.assertEqual(context.topological_order, ["n1", "n2", "n3"])

    def test_build_context_rejects_cycles(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "filter", "config": {
                    "input_key": "items",
                    "field": "amount",
                    "operator": "greater_than",
                    "value": "500",
                }},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n1"},
            ],
        }

        with self.assertRaises(ValueError):
            self.executor.build_context(definition)

    def test_execute_linear_workflow_from_manual_trigger(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "filter", "config": {
                    "input_key": "items",
                    "field": "amount",
                    "operator": "greater_than",
                    "value": "500",
                }},
                {"id": "n3", "type": "aggregate", "config": {
                    "input_key": "items",
                    "operation": "count",
                    "output_key": "matched_count",
                }},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={
                "items": [
                    {"amount": 300},
                    {"amount": 700},
                    {"amount": 900},
                ]
            },
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3"])
        self.assertEqual(result["node_outputs"]["n1"]["trigger_type"], "manual")
        self.assertEqual(result["node_outputs"]["n2"]["items"], [{"amount": 700}, {"amount": 900}])
        self.assertEqual(result["node_outputs"]["n3"], {"matched_count": 2})
        self.assertEqual(result["terminal_outputs"], {"n3": {"matched_count": 2}})

    def test_execute_if_else_routes_only_matching_branch(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "if_else", "config": {
                    "field": "status",
                    "operator": "equals",
                    "value": "paid",
                }},
                {"id": "n3", "type": "filter", "config": {
                    "input_key": "items",
                    "field": "amount",
                    "operator": "greater_than",
                    "value": "500",
                }},
                {"id": "n4", "type": "aggregate", "config": {
                    "input_key": "items",
                    "operation": "count",
                    "output_key": "low_count",
                }},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3", "branch": "true"},
                {"id": "e3", "source": "n2", "target": "n4", "branch": "false"},
            ],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={
                "status": "paid",
                "items": [
                    {"amount": 100},
                    {"amount": 650},
                ],
            },
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3"])
        self.assertIn("n3", result["node_outputs"])
        self.assertNotIn("n4", result["node_outputs"])
        self.assertNotIn("_branch", result["node_inputs"]["n3"])
        self.assertEqual(result["terminal_outputs"]["n3"]["items"], [{"amount": 650}])

    def test_execute_switch_routes_default_case(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "webhook_trigger", "config": {}},
                {"id": "n2", "type": "switch", "config": {
                    "field": "country",
                    "cases": [
                        {"label": "india", "operator": "equals", "value": "IN"},
                        {"label": "usa", "operator": "equals", "value": "US"},
                    ],
                    "default_case": "default",
                }},
                {"id": "n3", "type": "aggregate", "config": {
                    "input_key": "orders",
                    "operation": "count",
                    "output_key": "default_count",
                }},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3", "branch": "default"},
            ],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={
                "country": "JP",
                "orders": [{"id": 1}, {"id": 2}, {"id": 3}],
            },
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3"])
        self.assertEqual(result["node_outputs"]["n1"]["trigger_type"], "webhook")
        self.assertEqual(result["node_outputs"]["n3"], {"default_count": 3})

    def test_execute_merge_waits_for_all_parallel_parents(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "filter", "config": {
                    "input_key": "items",
                    "field": "amount",
                    "operator": "greater_than",
                    "value": "500",
                }},
                {"id": "n3", "type": "aggregate", "config": {
                    "input_key": "items",
                    "operation": "count",
                    "output_key": "item_count",
                }},
                {"id": "n4", "type": "merge", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n1", "target": "n3"},
                {"id": "e3", "source": "n2", "target": "n4"},
                {"id": "e4", "source": "n3", "target": "n4"},
            ],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={
                "items": [{"amount": 300}, {"amount": 700}],
            },
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3", "n4"])
        self.assertEqual(
            result["node_inputs"]["n4"],
            [
                {
                    "triggered": True,
                    "trigger_type": "manual",
                    "items": [{"amount": 700}],
                },
                {"item_count": 2},
            ],
        )
        self.assertEqual(
            result["node_outputs"]["n4"],
            {
                "merged": [
                    {
                        "triggered": True,
                        "trigger_type": "manual",
                        "items": [{"amount": 700}],
                    },
                    {"item_count": 2},
                ]
            },
        )

    def test_execute_merge_runs_after_untaken_branch_is_blocked(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "if_else", "config": {
                    "field": "status",
                    "operator": "equals",
                    "value": "paid",
                }},
                {"id": "n3", "type": "filter", "config": {
                    "input_key": "items",
                    "field": "amount",
                    "operator": "greater_than",
                    "value": "500",
                }},
                {"id": "n4", "type": "aggregate", "config": {
                    "input_key": "items",
                    "operation": "count",
                    "output_key": "failed_count",
                }},
                {"id": "n5", "type": "merge", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3", "branch": "true"},
                {"id": "e3", "source": "n2", "target": "n4", "branch": "false"},
                {"id": "e4", "source": "n3", "target": "n5"},
                {"id": "e5", "source": "n4", "target": "n5"},
            ],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={
                "status": "paid",
                "items": [{"amount": 100}, {"amount": 650}],
            },
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3", "n5"])
        self.assertEqual(
            context_state := result["node_outputs"]["n5"],
            {
                "merged": [
                    {
                        "triggered": True,
                        "trigger_type": "manual",
                        "status": "paid",
                        "items": [{"amount": 650}],
                    }
                ],
            },
        )
        self.assertEqual(result["terminal_outputs"], {"n5": context_state})

    def test_execute_rejects_unsupported_split_runtime(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "split_in", "config": {"input_key": "items"}},
                {"id": "n3", "type": "merge", "config": {}},
                {"id": "n4", "type": "split_out", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n3", "target": "n4"},
            ],
        }

        with self.assertRaises(NotImplementedError):
            self.executor.execute(
                definition=definition,
                initial_payload={"items": [{"id": 1}]},
            )

    def test_execute_split_in_and_split_out_reassemble_results(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "split_in", "config": {"input_key": "items"}},
                {"id": "n3", "type": "split_out", "config": {"output_key": "processed_items"}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={
                "items": [{"id": 1}, {"id": 2}, {"id": 3}],
            },
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3"])
        self.assertEqual(
            result["node_outputs"]["n3"],
            {
                "processed_items": [
                    {"item": {"id": 1}},
                    {"item": {"id": 2}},
                    {"item": {"id": 3}},
                ]
            },
        )

    def test_execute_split_in_empty_input_still_runs_split_out(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "split_in", "config": {"input_key": "items"}},
                {"id": "n3", "type": "split_out", "config": {"output_key": "results"}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={"items": []},
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3"])
        self.assertEqual(result["node_outputs"]["n3"], {"results": []})

    def test_execute_split_path_preserves_order_through_branching(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "split_in", "config": {"input_key": "items"}},
                {"id": "n3", "type": "if_else", "config": {
                    "field": "item.status",
                    "operator": "equals",
                    "value": "paid",
                }},
                {"id": "n4", "type": "split_out", "config": {"output_key": "results"}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n3", "target": "n4", "branch": "true"},
                {"id": "e4", "source": "n3", "target": "n4", "branch": "false"},
            ],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={
                "items": [
                    {"id": 1, "status": "paid"},
                    {"id": 2, "status": "failed"},
                    {"id": 3, "status": "paid"},
                ]
            },
        )

        self.assertEqual(
            result["node_outputs"]["n4"],
            {
                "results": [
                    {"item": {"id": 1, "status": "paid"}},
                    {"item": {"id": 2, "status": "failed"}},
                    {"item": {"id": 3, "status": "paid"}},
                ]
            },
        )

    def test_execute_unknown_frontend_node_as_dummy_pass_through(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "send_gmail_message", "config": {}},
                {"id": "n3", "type": "aggregate", "config": {
                    "input_key": "orders",
                    "operation": "count",
                    "output_key": "order_count",
                }},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={"orders": [{"id": 1}, {"id": 2}]},
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3"])
        self.assertEqual(result["node_outputs"]["n2"]["dummy_node_executed"], True)
        self.assertEqual(result["node_outputs"]["n2"]["dummy_node_type"], "send_gmail_message")
        self.assertEqual(result["node_outputs"]["n3"], {"order_count": 2})


if __name__ == "__main__":
    unittest.main()
