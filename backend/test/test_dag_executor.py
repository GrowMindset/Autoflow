import unittest
from unittest.mock import patch

from app.execution.dag_executor import DagExecutor, NodeExecutionError
from app.execution.registry import RunnerRegistry
from app.execution.runners.nodes.ai_agent import AIAgentRunner
from app.execution.runners.nodes.delay import DelayRunner
from app.execution.runners.nodes.dummy import DummyNodeRunner
from app.execution.runners.nodes.merge import MergeRunner


class _RecordingRunner:
    def __init__(self, result=None, calls=None):
        self.result = result or {}
        self.calls = calls if calls is not None else []

    def run(self, config, input_data, context=None):
        self.calls.append(
            {
                "config": config,
                "input_data": input_data,
                "context": context or {},
            }
        )
        if callable(self.result):
            return self.result(config, input_data, context or {})
        return self.result


class _FakeRegistry:
    def __init__(self, runners):
        self.runners = runners

    def get_runner(self, node_type):
        return self.runners[node_type]


class _CountingMergeRunner(MergeRunner):
    def __init__(self):
        super().__init__()
        self.calls: list[dict[str, object]] = []

    def run(self, config: dict, input_data: list, context=None) -> dict:
        self.calls.append(
            {
                "config": dict(config or {}),
                "input_data": list(input_data or []),
            }
        )
        return super().run(config=config, input_data=input_data, context=context)


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

    def test_runner_registry_registers_ai_agent_runner(self):
        runner = RunnerRegistry().get_runner("ai_agent")
        self.assertIsInstance(runner, AIAgentRunner)

    def test_runner_registry_routes_send_gmail_to_non_dummy_by_default(self):
        class _SentinelRunner:
            pass

        class _SafeRegistry(RunnerRegistry):
            @staticmethod
            def _build_send_gmail_message():
                return _SentinelRunner()

        runner = _SafeRegistry().get_runner("send_gmail_message")
        self.assertIsInstance(runner, _SentinelRunner)

    def test_runner_registry_can_force_legacy_dummy_node_via_env(self):
        with patch.dict(
            "os.environ",
            {"AUTOFLOW_LEGACY_DUMMY_NODE_TYPES": "send_gmail_message"},
            clear=False,
        ):
            runner = RunnerRegistry().get_runner("send_gmail_message")
        self.assertIsInstance(runner, DummyNodeRunner)

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

    def test_build_context_allows_cycles_when_loop_control_enabled(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "filter", "config": {
                    "input_key": "items",
                    "field": "amount",
                    "operator": "greater_than",
                    "value": "10",
                }},
                {"id": "n3", "type": "aggregate", "config": {
                    "input_key": "items",
                    "operation": "count",
                    "output_key": "count",
                }},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n3", "target": "n2"},
            ],
            "loop_control": {
                "enabled": True,
                "max_node_executions": 2,
                "max_total_node_executions": 10,
            },
        }

        context = self.executor.build_context(definition)

        self.assertTrue(context.loop_enabled)
        self.assertEqual(context.indegree["n2"], 2)
        self.assertEqual(context.indegree["n3"], 1)
        self.assertIn("n2", context.cycle_node_ids)
        self.assertIn("n3", context.cycle_node_ids)

    def test_execute_cycle_stops_at_per_node_loop_cap(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n2"},
            ],
            "loop_control": {
                "enabled": True,
                "max_node_executions": 2,
                "max_total_node_executions": 20,
            },
        }

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: {
                            "triggered": True,
                            "trigger_type": "manual",
                            **(input_data or {}),
                        }
                    ),
                    "echo": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: dict(input_data or {}),
                    ),
                }
            )
        )

        with self.assertRaises(NodeExecutionError) as exc_ctx:
            executor.execute(definition=definition, initial_payload={"seed": "x"})

        self.assertIn("max_node_executions=2", str(exc_ctx.exception))

    def test_execute_cycle_honors_total_execution_safety_cap(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n2"},
            ],
            "loop_control": {
                "enabled": True,
                "max_node_executions": 50,
                "max_total_node_executions": 3,
            },
        }

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: {
                            "triggered": True,
                            "trigger_type": "manual",
                            **(input_data or {}),
                        }
                    ),
                    "echo": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: dict(input_data or {}),
                    ),
                }
            )
        )

        with self.assertRaises(NodeExecutionError) as exc_ctx:
            executor.execute(definition=definition, initial_payload={"seed": "x"})

        self.assertIn("max_total_node_executions=3", str(exc_ctx.exception))

    def test_execute_cycle_uses_seeded_loop_runtime_state(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n2"},
            ],
            "loop_control": {
                "enabled": True,
                "max_node_executions": 2,
                "max_total_node_executions": 20,
            },
        }

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: {
                            "triggered": True,
                            "trigger_type": "manual",
                            **(input_data or {}),
                        }
                    ),
                    "echo": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: dict(input_data or {}),
                    ),
                }
            )
        )

        with self.assertRaises(NodeExecutionError) as exc_ctx:
            executor.execute(
                definition=definition,
                initial_payload={"seed": "x"},
                runner_context={
                    "loop_runtime_state": {
                        "total_node_executions": 2,
                        "node_execution_counts": {"n2": 1},
                    }
                },
            )

        self.assertIn("max_node_executions=2", str(exc_ctx.exception))

    def test_cycle_readiness_waits_for_all_cycle_feedback_inputs(self):
        n2_calls: list[dict] = []

        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "n2_echo", "config": {}},
                {"id": "n3", "type": "n3_echo", "config": {}},
                {"id": "n4", "type": "n4_echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2", "targetHandle": "seed"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n2", "target": "n4"},
                {"id": "e4", "source": "n3", "target": "n2", "targetHandle": "feedback_a"},
                {"id": "e5", "source": "n4", "target": "n2", "targetHandle": "feedback_b"},
            ],
            "loop_control": {
                "enabled": True,
                "max_node_executions": 2,
                "max_total_node_executions": 20,
            },
        }

        def _manual_trigger(_config, input_data, _ctx):
            return {
                "triggered": True,
                "trigger_type": "manual",
                **(input_data or {}),
            }

        def _record_n2(_config, input_data, _ctx):
            snapshot = dict(input_data or {}) if isinstance(input_data, dict) else {"_default": input_data}
            n2_calls.append(snapshot)
            return snapshot

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(result=_manual_trigger),
                    "n2_echo": _RecordingRunner(result=_record_n2),
                    "n3_echo": _RecordingRunner(result=lambda _config, input_data, _ctx: dict(input_data or {})),
                    "n4_echo": _RecordingRunner(result=lambda _config, input_data, _ctx: dict(input_data or {})),
                }
            )
        )

        with self.assertRaises(NodeExecutionError) as exc_ctx:
            executor.execute(definition=definition, initial_payload={"seed_value": "x"})

        self.assertIn("max_node_executions=2", str(exc_ctx.exception))
        self.assertEqual(len(n2_calls), 2)
        second_input = n2_calls[1]
        self.assertIn("feedback_a", second_input)
        self.assertIn("feedback_b", second_input)

    def test_cycle_total_cap_does_not_starve_sibling_feedback_branch(self):
        n2_calls = []
        n3_calls = []
        n4_calls = []

        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "echo", "config": {}},
                {"id": "n3", "type": "echo", "config": {}},
                {"id": "n4", "type": "echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2", "targetHandle": "seed"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n2", "target": "n4"},
                {"id": "e4", "source": "n3", "target": "n2", "targetHandle": "feedback_a"},
                {"id": "e5", "source": "n4", "target": "n2", "targetHandle": "feedback_b"},
            ],
            "loop_control": {
                "enabled": True,
                "max_node_executions": 50,
                "max_total_node_executions": 7,
            },
        }

        def _manual_trigger(_config, input_data, _ctx):
            return {
                "triggered": True,
                "trigger_type": "manual",
                **(input_data or {}),
            }

        def _record_n2(_config, input_data, _ctx):
            payload = dict(input_data or {}) if isinstance(input_data, dict) else {"_default": input_data}
            n2_calls.append(payload)
            return payload

        def _record_n3(_config, input_data, _ctx):
            payload = dict(input_data or {}) if isinstance(input_data, dict) else {"_default": input_data}
            n3_calls.append(payload)
            return payload

        def _record_n4(_config, input_data, _ctx):
            payload = dict(input_data or {}) if isinstance(input_data, dict) else {"_default": input_data}
            n4_calls.append(payload)
            return payload

        class _LoopRegistry:
            def get_runner(self, node_type):
                if node_type == "manual_trigger":
                    return _RecordingRunner(result=_manual_trigger)
                if node_type == "n2_echo":
                    return _RecordingRunner(result=_record_n2)
                if node_type == "n3_echo":
                    return _RecordingRunner(result=_record_n3)
                if node_type == "n4_echo":
                    return _RecordingRunner(result=_record_n4)
                raise KeyError(node_type)

        rewritten_definition = {
            **definition,
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "n2_echo", "config": {}},
                {"id": "n3", "type": "n3_echo", "config": {}},
                {"id": "n4", "type": "n4_echo", "config": {}},
            ],
        }

        executor = DagExecutor(registry=_LoopRegistry())

        with self.assertRaises(NodeExecutionError) as exc_ctx:
            executor.execute(definition=rewritten_definition, initial_payload={"seed_value": "x"})

        self.assertIn("max_total_node_executions=7", str(exc_ctx.exception))
        self.assertGreaterEqual(len(n3_calls), 1)
        self.assertGreaterEqual(len(n4_calls), 1)
        self.assertEqual(len(n2_calls), 2)

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

    def test_execute_emits_node_progress_events(self):
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
            ],
        }

        events: list[tuple[str, str]] = []

        self.executor.execute(
            definition=definition,
            initial_payload={"items": [{"amount": 100}, {"amount": 700}]},
            progress_callback=lambda **event: events.append(
                (event.get("node_id", ""), event.get("status", ""))
            ),
        )

        self.assertEqual(
            events,
            [
                ("n1", "RUNNING"),
                ("n1", "SUCCEEDED"),
                ("n2", "RUNNING"),
                ("n2", "SUCCEEDED"),
            ],
        )

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
                {"id": "n4", "type": "merge", "config": {"mode": "append"}},
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

    def test_execute_merge_choose_branch_supports_multiple_input_handles(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "tag_output", "config": {"tag": "one"}},
                {"id": "n3", "type": "tag_output", "config": {"tag": "two"}},
                {"id": "n4", "type": "tag_output", "config": {"tag": "three"}},
                {"id": "n5", "type": "merge", "config": {"mode": "choose_branch", "choose_branch": "input3", "input_count": 3}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n1", "target": "n3"},
                {"id": "e3", "source": "n1", "target": "n4"},
                {"id": "e4", "source": "n2", "target": "n5", "targetHandle": "input1"},
                {"id": "e5", "source": "n3", "target": "n5", "targetHandle": "input2"},
                {"id": "e6", "source": "n4", "target": "n5", "targetHandle": "input3"},
            ],
        }

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: {
                            "triggered": True,
                            "trigger_type": "manual",
                            **(input_data or {}),
                        }
                    ),
                    "tag_output": _RecordingRunner(
                        result=lambda config, input_data, _ctx: {
                            "tag": str(config.get("tag") or ""),
                            **(input_data or {}),
                        }
                    ),
                    "merge": MergeRunner(),
                }
            )
        )

        result = executor.execute(
            definition=definition,
            initial_payload={"seed": "x"},
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3", "n4", "n5"])
        self.assertEqual(
            result["node_outputs"]["n5"],
            {"tag": "three", "triggered": True, "trigger_type": "manual", "seed": "x"},
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

    def test_branching_blocks_untaken_paths_before_deferred_merge_schedule(self):
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

        events: list[tuple[str, str, str]] = []

        def _progress_callback(
            *,
            node_id: str,
            node_type: str,
            status: str,
            input_data=None,
            output_data=None,
            error_message=None,
        ) -> None:
            if node_id in {"n3", "n4"} and status in {"SUCCEEDED", "SKIPPED"}:
                events.append(("progress", node_id, status))

        def _defer_callback(
            *,
            source_node_id: str,
            source_node_type: str,
            target_node_id: str,
            target_handle: str | None,
            payload,
            delay_seconds: float,
            delay_run_at=None,
            loop_runtime_state=None,
        ) -> None:
            if source_node_id == "n3" and target_node_id == "n5":
                events.append(("defer", source_node_id, target_node_id))

        self.executor.execute(
            definition=definition,
            initial_payload={
                "status": "paid",
                "items": [{"amount": 100}, {"amount": 650}],
            },
            progress_callback=_progress_callback,
            defer_callback=_defer_callback,
        )

        skipped_index = events.index(("progress", "n4", "SKIPPED"))
        defer_index = events.index(("defer", "n3", "n5"))
        self.assertLess(skipped_index, defer_index)

    def test_blocked_path_executes_node_when_pending_input_already_present(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "if_else", "config": {}},
                {"id": "n3", "type": "echo", "config": {}},
                {"id": "n4", "type": "echo", "config": {}},
                {"id": "n5", "type": "echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3", "branch": "true"},
                {"id": "e3", "source": "n2", "target": "n4", "branch": "false"},
                {"id": "e4", "source": "n3", "target": "n5"},
                {"id": "e5", "source": "n4", "target": "n5"},
            ],
        }

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: dict(input_data or {}),
                    ),
                    "if_else": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: dict(input_data or {}),
                    ),
                    "echo": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: dict(input_data or {}),
                    ),
                }
            )
        )

        context = executor.build_context(definition)
        context.runner_context = {}

        # Simulate one successful upstream result arriving first.
        executor._execute_from_node(
            context=context,
            node_id="n5",
            input_data={"student_email": "a@test.com"},
            target_handle=None,
        )
        self.assertEqual(context.node_states["n5"], "pending")

        # Simulate the other upstream branch being blocked later.
        executor._block_path(context=context, node_id="n5")

        # Node should execute now because one real input + one blocked input account
        # for all indegree inputs.
        self.assertEqual(context.node_states["n5"], "completed")
        self.assertIn("n5", context.visited_nodes)
        self.assertEqual(
            context.node_outputs["n5"],
            {"student_email": "a@test.com"},
        )

    def test_merge_resume_payload_is_deterministic_with_in_memory_persistence(self):
        definition = {
            "nodes": [
                {"id": "a", "type": "echo", "config": {}},
                {"id": "b", "type": "echo", "config": {}},
                {"id": "merge_1", "type": "merge", "config": {"mode": "append"}},
            ],
            "edges": [
                {"id": "e1", "source": "a", "target": "merge_1", "targetHandle": "input1"},
                {"id": "e2", "source": "b", "target": "merge_1", "targetHandle": "input2"},
            ],
        }

        merge_runner = _CountingMergeRunner()
        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "merge": merge_runner,
                    "echo": _RecordingRunner(result=lambda _config, input_data, _ctx: dict(input_data or {})),
                }
            )
        )
        context = executor.build_context(definition)
        context.runner_context = {}

        in_memory_state: dict[str, dict[str, object]] = {}

        def _build_resume_payload(blocked_inputs: int = 0) -> dict[str, object]:
            return {
                "__merge_inputs__": [in_memory_state[key] for key in sorted(in_memory_state.keys())],
                "__merge_blocked_inputs__": blocked_inputs,
            }

        in_memory_state["a"] = {"handle": "input1", "data": {"source": "A"}}
        executor._execute_from_node(
            context=context,
            node_id="merge_1",
            input_data=_build_resume_payload(blocked_inputs=0),
        )
        self.assertEqual(context.node_states["merge_1"], "pending")
        self.assertEqual(len(merge_runner.calls), 0)

        in_memory_state["b"] = {"handle": "input2", "data": {"source": "B"}}
        executor._execute_from_node(
            context=context,
            node_id="merge_1",
            input_data=_build_resume_payload(blocked_inputs=0),
        )

        self.assertEqual(context.node_states["merge_1"], "completed")
        self.assertEqual(len(merge_runner.calls), 1)
        self.assertEqual(
            context.node_outputs["merge_1"],
            {"merged": [{"source": "A"}, {"source": "B"}]},
        )
        self.assertEqual(context.visited_nodes.count("merge_1"), 1)
        self.assertEqual(context.pending_inputs["merge_1"], [])

    def test_merge_resume_payload_accounts_for_blocked_inputs_without_external_state(self):
        definition = {
            "nodes": [
                {"id": "a", "type": "echo", "config": {}},
                {"id": "b", "type": "echo", "config": {}},
                {"id": "merge_1", "type": "merge", "config": {"mode": "append"}},
            ],
            "edges": [
                {"id": "e1", "source": "a", "target": "merge_1", "targetHandle": "input1"},
                {"id": "e2", "source": "b", "target": "merge_1", "targetHandle": "input2"},
            ],
        }
        merge_runner = _CountingMergeRunner()
        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "merge": merge_runner,
                    "echo": _RecordingRunner(result=lambda _config, input_data, _ctx: dict(input_data or {})),
                }
            )
        )
        context = executor.build_context(definition)
        context.runner_context = {}

        resume_payload = {
            "__merge_inputs__": [{"handle": "input1", "data": {"source": "A"}}],
            "__merge_blocked_inputs__": 1,
        }
        executor._execute_from_node(
            context=context,
            node_id="merge_1",
            input_data=resume_payload,
        )

        self.assertEqual(context.node_states["merge_1"], "completed")
        self.assertEqual(len(merge_runner.calls), 1)
        self.assertEqual(
            context.node_outputs["merge_1"],
            {"merged": [{"source": "A"}]},
        )

    def test_branch_accounting_unblocks_non_merge_join_exactly_once(self):
        join_runner = _RecordingRunner(result=lambda _config, input_data, _ctx: dict(input_data or {}))
        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "echo": join_runner,
                }
            )
        )
        definition = {
            "nodes": [
                {"id": "left", "type": "echo", "config": {}},
                {"id": "right", "type": "echo", "config": {}},
                {"id": "join", "type": "echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "left", "target": "join"},
                {"id": "e2", "source": "right", "target": "join"},
            ],
        }

        context = executor.build_context(definition)
        context.runner_context = {}

        executor._execute_from_node(
            context=context,
            node_id="join",
            input_data={"selected": True},
        )
        self.assertEqual(context.node_states["join"], "pending")
        self.assertEqual(len(join_runner.calls), 0)

        executor._block_path(context=context, node_id="join")
        self.assertEqual(context.node_states["join"], "completed")
        self.assertEqual(len(join_runner.calls), 1)
        self.assertEqual(context.visited_nodes.count("join"), 1)

        # Invariant: duplicate blocked notifications must not trigger a second run.
        executor._block_path(context=context, node_id="join")
        executor._execute_from_node(
            context=context,
            node_id="join",
            input_data={"late": True},
        )
        self.assertEqual(len(join_runner.calls), 1)
        self.assertEqual(context.visited_nodes.count("join"), 1)

    def test_branch_accounting_unblocks_merge_join_exactly_once(self):
        merge_runner = _CountingMergeRunner()
        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "merge": merge_runner,
                    "echo": _RecordingRunner(result=lambda _config, input_data, _ctx: dict(input_data or {})),
                }
            )
        )
        definition = {
            "nodes": [
                {"id": "left", "type": "echo", "config": {}},
                {"id": "right", "type": "echo", "config": {}},
                {"id": "join", "type": "merge", "config": {"mode": "append"}},
            ],
            "edges": [
                {"id": "e1", "source": "left", "target": "join", "targetHandle": "input1"},
                {"id": "e2", "source": "right", "target": "join", "targetHandle": "input2"},
            ],
        }

        context = executor.build_context(definition)
        context.runner_context = {}

        executor._execute_from_node(
            context=context,
            node_id="join",
            input_data={"selected": "left"},
            target_handle="input1",
        )
        self.assertEqual(context.node_states["join"], "pending")
        self.assertEqual(len(merge_runner.calls), 0)

        executor._block_path(context=context, node_id="join")
        self.assertEqual(context.node_states["join"], "completed")
        self.assertEqual(len(merge_runner.calls), 1)
        self.assertEqual(context.visited_nodes.count("join"), 1)
        self.assertEqual(
            context.node_outputs["join"],
            {"merged": [{"selected": "left"}]},
        )

        # Invariant: duplicate blocked notifications must not trigger merge again.
        executor._block_path(context=context, node_id="join")
        self.assertEqual(len(merge_runner.calls), 1)
        self.assertEqual(context.visited_nodes.count("join"), 1)

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
                {"id": "n2", "type": "custom_dummy_node", "config": {}},
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
        self.assertEqual(result["node_outputs"]["n2"]["dummy_node_type"], "custom_dummy_node")
        self.assertEqual(result["node_outputs"]["n3"], {"order_count": 2})

    def test_execute_inline_subnodes_before_ai_agent_and_injects_api_key(self):
        call_order: list[str] = []

        class ChatModelRunner:
            def run(self, config, input_data, context=None):
                call_order.append("chat_model")
                return {
                    "provider": "openai",
                    "model": config["model"],
                    "credential_id": config["credential_id"],
                    "options": {
                        "temperature": config["temperature"],
                        "max_tokens": config["max_tokens"],
                    },
                }

        class AgentRunner:
            def run(self, config, input_data, context=None):
                call_order.append("ai_agent")
                return {
                    "seen_config": config,
                    "seen_input": input_data,
                }

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: {
                            "triggered": True,
                            "trigger_type": "manual",
                            **(input_data or {}),
                        }
                    ),
                    "chat_model_openai": ChatModelRunner(),
                    "ai_agent": AgentRunner(),
                }
            )
        )
        definition = {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "config": {}},
                {
                    "id": "agent",
                    "type": "ai_agent",
                    "config": {
                        "system_prompt": "System {{trigger.customer.name}}",
                        "command": "Reply to {{trigger.customer.name}}",
                    },
                },
                {
                    "id": "chat_cfg",
                    "type": "chat_model_openai",
                    "config": {
                        "credential_id": "cred-1",
                        "model": "gpt-4o-mini",
                        "temperature": 0.2,
                        "max_tokens": 128,
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger", "target": "agent"},
                {
                    "id": "e2",
                    "source": "chat_cfg",
                    "target": "agent",
                    "targetHandle": "chat_model",
                },
            ],
        }

        result = executor.execute(
            definition=definition,
            initial_payload={"customer": {"name": "Asha"}},
            runner_context={"resolved_credentials": {"cred-1": "secret-key"}},
        )

        self.assertEqual(call_order, ["chat_model", "ai_agent"])
        self.assertEqual(
            result["node_inputs"]["agent"]["chat_model"],
            {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "credential_id": "cred-1",
                "api_key": "secret-key",
                "options": {
                    "temperature": 0.2,
                    "max_tokens": 128,
                },
            },
        )
        self.assertEqual(
            result["node_outputs"]["agent"]["seen_config"],
            {
                "system_prompt": "System Asha",
                "command": "Reply to Asha",
            },
        )

    def test_execute_node_runs_inline_subnodes_before_runner(self):
        call_order: list[str] = []

        class ChatModelRunner:
            def run(self, config, input_data, context=None):
                call_order.append("chat_model")
                return {
                    "provider": "groq",
                    "model": config["model"],
                    "credential_id": config["credential_id"],
                    "options": {},
                }

        agent_runner = _RecordingRunner(
            result=lambda config, input_data, _ctx: {
                "config": config,
                "input": input_data,
            },
            calls=[],
        )

        class OrderedAgentRunner:
            def run(self, config, input_data, context=None):
                call_order.append("ai_agent")
                return agent_runner.run(config, input_data, context)

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "chat_model_groq": ChatModelRunner(),
                    "ai_agent": OrderedAgentRunner(),
                }
            )
        )

        result = executor.execute_node(
            node_id="agent",
            node_type="ai_agent",
            config={"command": "Summarize {{customer.name}}", "system_prompt": "Helper"},
            input_data={"customer": {"name": "Mina"}},
            runner_context={"resolved_credentials": {"cred-9": "groq-key"}},
            subnode_configs=[
                {
                    "node_id": "chat_cfg",
                    "node_type": "chat_model_groq",
                    "target_handle": "chat_model",
                    "config": {
                        "credential_id": "cred-9",
                        "model": "llama-3.3-70b-versatile",
                    },
                }
            ],
        )

        self.assertEqual(call_order, ["chat_model", "ai_agent"])
        self.assertEqual(
            result["input_data"]["chat_model"],
            {
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "credential_id": "cred-9",
                "api_key": "groq-key",
                "options": {},
            },
        )
        self.assertEqual(result["output_data"]["config"]["command"], "Summarize Mina")

    def test_form_payload_templates_support_flat_and_form_namespaced_paths(self):
        class FormTriggerRunner:
            def run(self, config, input_data, context=None):
                return {
                    "triggered": True,
                    "trigger_type": "form",
                    **(input_data or {}),
                }

        class EchoRunner:
            def run(self, config, input_data, context=None):
                return {"seen_config": config}

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "form_trigger": FormTriggerRunner(),
                    "echo": EchoRunner(),
                }
            )
        )

        definition = {
            "nodes": [
                {
                    "id": "trigger",
                    "type": "form_trigger",
                    "config": {
                        "fields": [
                            {"name": "article_topic", "required": True},
                            {"name": "tone", "required": True},
                        ]
                    },
                },
                {
                    "id": "echo_1",
                    "type": "echo",
                    "config": {
                        "flat_topic": "{{article_topic}}",
                        "form_topic": "{{form.article_topic}}",
                        "trigger_tone": "{{trigger.tone}}",
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger", "target": "echo_1"},
            ],
        }

        result = executor.execute(
            definition=definition,
            initial_payload={"article_topic": "AI automation", "tone": "friendly"},
        )

        self.assertEqual(result["visited_nodes"], ["trigger", "echo_1"])
        self.assertEqual(
            result["node_outputs"]["echo_1"]["seen_config"],
            {
                "flat_topic": "AI automation",
                "form_topic": "AI automation",
                "trigger_tone": "friendly",
            },
        )

    def test_execute_node_expression_mode_resolves_templates_and_strips_metadata(self):
        recorder = _RecordingRunner(
            result=lambda config, _input_data, _ctx: {"seen_config": config},
        )
        executor = DagExecutor(registry=_FakeRegistry({"echo": recorder}))

        result = executor.execute_node(
            node_id="echo_1",
            node_type="echo",
            config={
                "subject": "Hello {{name}}",
                "__af_mode": {"subject": "expression"},
                "__af_values": {
                    "subject": {
                        "fixed": "Hello {{name}}",
                        "expression": "Hello {{name}}",
                    }
                },
            },
            input_data={"name": "Mina"},
        )

        seen_config = result["output_data"]["seen_config"]
        self.assertEqual(seen_config["subject"], "Hello Mina")
        self.assertNotIn("__af_mode", seen_config)
        self.assertNotIn("__af_values", seen_config)

    def test_execute_node_fixed_mode_keeps_literal_templates_and_strips_metadata(self):
        recorder = _RecordingRunner(
            result=lambda config, _input_data, _ctx: {"seen_config": config},
        )
        executor = DagExecutor(registry=_FakeRegistry({"echo": recorder}))

        result = executor.execute_node(
            node_id="echo_1",
            node_type="echo",
            config={
                "subject": "Hello {{name}}",
                "__af_mode": {"subject": "fixed"},
                "__af_values": {
                    "subject": {
                        "fixed": "Hello {{name}}",
                        "expression": "Hello {{name}}",
                    }
                },
            },
            input_data={"name": "Mina"},
        )

        seen_config = result["output_data"]["seen_config"]
        self.assertEqual(seen_config["subject"], "Hello {{name}}")
        self.assertNotIn("__af_mode", seen_config)
        self.assertNotIn("__af_values", seen_config)

    def test_execute_workflow_expression_mode_resolves_templates_and_strips_metadata(self):
        class ManualTriggerRunner:
            def run(self, config, input_data, context=None):
                return {
                    "triggered": True,
                    "trigger_type": "manual",
                    **(input_data or {}),
                }

        class EchoRunner:
            def run(self, config, input_data, context=None):
                return {
                    "seen_config": config,
                    "seen_input": input_data,
                }

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": ManualTriggerRunner(),
                    "echo": EchoRunner(),
                }
            )
        )

        definition = {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "config": {}},
                {
                    "id": "echo_1",
                    "type": "echo",
                    "config": {
                        "subject": "Hello {{name}}",
                        "__af_mode": {"subject": "expression"},
                        "__af_values": {
                            "subject": {
                                "fixed": "Hello {{name}}",
                                "expression": "Hello {{name}}",
                            }
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger", "target": "echo_1"},
            ],
        }

        result = executor.execute(
            definition=definition,
            initial_payload={"name": "Mina"},
        )

        seen_config = result["node_outputs"]["echo_1"]["seen_config"]
        self.assertEqual(seen_config["subject"], "Hello Mina")
        self.assertNotIn("__af_mode", seen_config)
        self.assertNotIn("__af_values", seen_config)

    def test_execute_workflow_fixed_mode_keeps_literal_templates_and_strips_metadata(self):
        class ManualTriggerRunner:
            def run(self, config, input_data, context=None):
                return {
                    "triggered": True,
                    "trigger_type": "manual",
                    **(input_data or {}),
                }

        class EchoRunner:
            def run(self, config, input_data, context=None):
                return {
                    "seen_config": config,
                    "seen_input": input_data,
                }

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": ManualTriggerRunner(),
                    "echo": EchoRunner(),
                }
            )
        )

        definition = {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "config": {}},
                {
                    "id": "echo_1",
                    "type": "echo",
                    "config": {
                        "subject": "Hello {{name}}",
                        "__af_mode": {"subject": "fixed"},
                        "__af_values": {
                            "subject": {
                                "fixed": "Hello {{name}}",
                                "expression": "Hello {{name}}",
                            }
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger", "target": "echo_1"},
            ],
        }

        result = executor.execute(
            definition=definition,
            initial_payload={"name": "Mina"},
        )

        seen_config = result["node_outputs"]["echo_1"]["seen_config"]
        self.assertEqual(seen_config["subject"], "Hello {{name}}")
        self.assertNotIn("__af_mode", seen_config)
        self.assertNotIn("__af_values", seen_config)

    def test_execute_node_ignores_incomplete_mode_metadata_and_uses_legacy_resolution(self):
        recorder = _RecordingRunner(
            result=lambda config, _input_data, _ctx: {"seen_config": config},
        )
        executor = DagExecutor(registry=_FakeRegistry({"echo": recorder}))

        result = executor.execute_node(
            node_id="echo_1",
            node_type="echo",
            config={
                "subject": "Hello {{name}}",
                "__af_mode": {"subject": "fixed"},
                # Incomplete metadata: values object missing for field.
            },
            input_data={"name": "Mina"},
        )

        seen_config = result["output_data"]["seen_config"]
        # Falls back to legacy behavior (resolve templates) if metadata is malformed.
        self.assertEqual(seen_config["subject"], "Hello Mina")
        self.assertNotIn("__af_mode", seen_config)
        self.assertNotIn("__af_values", seen_config)

    def test_execute_workflow_ignores_incomplete_mode_metadata_and_uses_legacy_resolution(self):
        class ManualTriggerRunner:
            def run(self, config, input_data, context=None):
                return {
                    "triggered": True,
                    "trigger_type": "manual",
                    **(input_data or {}),
                }

        class EchoRunner:
            def run(self, config, input_data, context=None):
                return {
                    "seen_config": config,
                    "seen_input": input_data,
                }

        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": ManualTriggerRunner(),
                    "echo": EchoRunner(),
                }
            )
        )

        definition = {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "config": {}},
                {
                    "id": "echo_1",
                    "type": "echo",
                    "config": {
                        "subject": "Hello {{name}}",
                        "__af_mode": {"subject": "fixed"},
                        # Incomplete metadata: values object missing for field.
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger", "target": "echo_1"},
            ],
        }

        result = executor.execute(
            definition=definition,
            initial_payload={"name": "Mina"},
        )

        seen_config = result["node_outputs"]["echo_1"]["seen_config"]
        self.assertEqual(seen_config["subject"], "Hello Mina")
        self.assertNotIn("__af_mode", seen_config)
        self.assertNotIn("__af_values", seen_config)

    def test_execute_delay_defers_downstream_edges_when_delay_positive(self):
        deferred_calls: list[dict[str, object]] = []
        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: {
                            "triggered": True,
                            "trigger_type": "manual",
                            **(input_data or {}),
                        }
                    ),
                    "delay": DelayRunner(),
                    "echo": _RecordingRunner(result={"ok": True}),
                }
            )
        )
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "delay", "config": {"amount": "1", "unit": "seconds"}},
                {"id": "n3", "type": "echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        result = executor.execute(
            definition=definition,
            initial_payload={"name": "Asha"},
            defer_callback=lambda **kwargs: deferred_calls.append(kwargs),
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2"])
        self.assertNotIn("n3", result["node_outputs"])
        self.assertEqual(len(deferred_calls), 1)
        self.assertEqual(deferred_calls[0]["source_node_id"], "n2")
        self.assertEqual(deferred_calls[0]["target_node_id"], "n3")
        self.assertIn("loop_runtime_state", deferred_calls[0])

    def test_execute_defers_immediate_parallel_fanout_for_independent_branches(self):
        deferred_calls: list[dict[str, object]] = []
        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: {
                            "triggered": True,
                            "trigger_type": "manual",
                            **(input_data or {}),
                        }
                    ),
                    "echo": _RecordingRunner(result={"ok": True}),
                }
            )
        )
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "echo", "config": {}},
                {"id": "n3", "type": "echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n1", "target": "n3"},
            ],
        }

        result = executor.execute(
            definition=definition,
            initial_payload={"name": "Asha"},
            defer_callback=lambda **kwargs: deferred_calls.append(kwargs),
        )

        self.assertEqual(result["visited_nodes"], ["n1"])
        self.assertEqual(len(deferred_calls), 2)
        self.assertEqual(
            {str(item["target_node_id"]) for item in deferred_calls},
            {"n2", "n3"},
        )
        self.assertTrue(all(float(item["delay_seconds"]) == 0.0 for item in deferred_calls))

    def test_execute_keeps_inline_path_when_fanout_reaches_join_node(self):
        deferred_calls: list[dict[str, object]] = []
        executor = DagExecutor(
            registry=_FakeRegistry(
                {
                    "manual_trigger": _RecordingRunner(
                        result=lambda _config, input_data, _ctx: {
                            "triggered": True,
                            "trigger_type": "manual",
                            **(input_data or {}),
                        }
                    ),
                    "echo": _RecordingRunner(result=lambda _config, input_data, _ctx: input_data or {}),
                }
            )
        )
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "echo", "config": {}},
                {"id": "n3", "type": "echo", "config": {}},
                {"id": "n4", "type": "echo", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n1", "target": "n3"},
                {"id": "e3", "source": "n2", "target": "n4"},
                {"id": "e4", "source": "n3", "target": "n4"},
            ],
        }

        result = executor.execute(
            definition=definition,
            initial_payload={"value": 42},
            defer_callback=lambda **kwargs: deferred_calls.append(kwargs),
        )

        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n3", "n4"])
        self.assertEqual(deferred_calls, [])

    def test_execute_allows_explicit_non_trigger_start_node(self):
        definition = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "filter", "config": {
                    "input_key": "items",
                    "field": "amount",
                    "operator": "greater_than",
                    "value": "100",
                }},
            ],
            "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
        }

        result = self.executor.execute(
            definition=definition,
            initial_payload={"items": [{"amount": 50}, {"amount": 150}]},
            start_node_id="n2",
        )

        self.assertEqual(result["visited_nodes"], ["n2"])
        self.assertEqual(result["node_outputs"]["n2"]["items"], [{"amount": 150}])


if __name__ == "__main__":
    unittest.main()
