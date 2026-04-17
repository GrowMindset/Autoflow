import unittest

from app.execution.dag_executor import DagExecutor, NodeExecutionError
from app.execution.registry import RunnerRegistry
from app.execution.runners.nodes.ai_agent import AIAgentRunner


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
        self.assertEqual(context.indegree["n2"], 1)
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

        result = executor.execute(definition=definition, initial_payload={"seed": "x"})

        self.assertEqual(result["node_execution_counts"]["n1"], 1)
        self.assertEqual(result["node_execution_counts"]["n2"], 2)
        self.assertEqual(result["total_node_executions"], 3)
        self.assertEqual(result["visited_nodes"], ["n1", "n2", "n2"])

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


if __name__ == "__main__":
    unittest.main()
