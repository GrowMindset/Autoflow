import json
import re
from collections import deque
from typing import Any, Callable

from app.execution.context import ExecutionContext
from app.execution.registry import RunnerRegistry


TRIGGER_NODE_TYPES = {"manual_trigger", "form_trigger", "schedule_trigger", "webhook_trigger", "workflow_trigger"}
BRANCHING_NODE_TYPES = {"if_else", "switch"}
UNSUPPORTED_RUNTIME_NODE_TYPES = set()

# Sub-nodes are configuration helpers (e.g. Chat Model selectors) that attach to
# the *bottom* of a parent node via a named handle.  They are NOT part of the main
# data-flow and must NOT be counted toward the parent node's indegree.  Instead,
# the executor runs them automatically (inline) just before the parent executes,
# and injects their output into the parent's input under the targetHandle key.
SUBNODE_TYPES = {"chat_model_openai", "chat_model_groq"}
LOOP_CONTROL_DEFAULTS = {
    "enabled": False,
    "max_node_executions": 3,
    "max_total_node_executions": 500,
}


class NodeExecutionError(Exception):
    def __init__(
        self,
        *,
        node_id: str,
        node_type: str,
        input_data: Any,
        original_exception: Exception,
        visited_nodes: list[str] | None = None,
        node_inputs: dict[str, Any] | None = None,
        node_outputs: dict[str, Any] | None = None,
    ) -> None:
        self.node_id = node_id
        self.node_type = node_type
        self.input_data = input_data
        self.original_exception = original_exception
        self.visited_nodes = visited_nodes or []
        self.node_inputs = node_inputs or {}
        self.node_outputs = node_outputs or {}
        super().__init__(str(original_exception))


class WorkflowStopRequested(Exception):
    """Raised by progress callbacks when a running execution is manually stopped."""


class DagExecutor:
    """Executes dummy workflow JSON in memory."""

    def __init__(self, registry: RunnerRegistry | None = None) -> None:
        self.registry = registry or RunnerRegistry()
        self._progress_callback: Callable[..., None] | None = None
        self._defer_callback: Callable[..., None] | None = None
        self._parallel_fanout_enabled = True

    def execute(
        self,
        definition: dict[str, Any],
        initial_payload: dict[str, Any] | None = None,
        start_node_id: str | None = None,
        start_target_handle: str | None = None,
        runner_context: dict[str, Any] | None = None,
        progress_callback: Callable[..., None] | None = None,
        defer_callback: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        self._progress_callback = progress_callback
        self._defer_callback = defer_callback
        context = self.build_context(definition)
        context.runner_context = runner_context or {}
        self._parallel_fanout_enabled = bool(
            (context.runner_context or {}).get("parallel_fanout_enabled", True)
        )
        self._seed_loop_runtime_state(context=context)
        chosen_start_node_id = start_node_id or self._resolve_start_node(context)

        if chosen_start_node_id not in context.nodes_by_id:
            raise ValueError(f"Start node '{chosen_start_node_id}' was not found")

        start_node = context.nodes_by_id[chosen_start_node_id]
        if start_node_id is None and start_node["type"] not in TRIGGER_NODE_TYPES:
            raise ValueError(
                f"Start node '{chosen_start_node_id}' must be a trigger node"
            )

        try:
            self._execute_from_node(
                context=context,
                node_id=chosen_start_node_id,
                input_data=initial_payload,
                target_handle=start_target_handle,
            )
        except NodeExecutionError as exc:
            # Preserve partial progress so callers can persist exactly how far
            # the workflow ran before failing.
            exc.visited_nodes = list(context.visited_nodes)
            exc.node_inputs = dict(context.node_inputs)
            exc.node_outputs = dict(context.node_outputs)
            raise
        finally:
            self._progress_callback = None
            self._defer_callback = None
            self._parallel_fanout_enabled = True

        terminal_outputs = {
            node_id: context.node_outputs[node_id]
            for node_id in context.visited_nodes
            if len(context.outgoing_edges.get(node_id, [])) == 0
        }

        return {
            "topological_order": context.topological_order,
            "visited_nodes": context.visited_nodes,
            "node_inputs": context.node_inputs,
            "node_outputs": context.node_outputs,
            "terminal_outputs": terminal_outputs,
            "loop_enabled": context.loop_enabled,
            "node_execution_counts": context.node_execution_counts,
            "total_node_executions": context.total_node_executions,
        }

    @staticmethod
    def _seed_loop_runtime_state(*, context: ExecutionContext) -> None:
        if not context.loop_enabled:
            return
        runtime_state = (context.runner_context or {}).get("loop_runtime_state")
        if not isinstance(runtime_state, dict):
            return

        raw_total = runtime_state.get("total_node_executions")
        try:
            seeded_total = max(0, int(raw_total))
        except Exception:
            seeded_total = 0
        context.total_node_executions = max(context.total_node_executions, seeded_total)

        raw_counts = runtime_state.get("node_execution_counts")
        if not isinstance(raw_counts, dict):
            return

        for node_id, raw_count in raw_counts.items():
            if node_id not in context.node_execution_counts:
                continue
            try:
                seeded_count = max(0, int(raw_count))
            except Exception:
                continue
            context.node_execution_counts[node_id] = max(
                context.node_execution_counts[node_id],
                seeded_count,
            )

    @staticmethod
    def _loop_runtime_state_snapshot(*, context: ExecutionContext) -> dict[str, Any] | None:
        if not context.loop_enabled:
            return None
        return {
            "total_node_executions": int(context.total_node_executions),
            "node_execution_counts": {
                node_id: int(count)
                for node_id, count in context.node_execution_counts.items()
                if int(count) > 0
            },
        }

    def execute_node(
        self,
        *,
        node_id: str,
        node_type: str,
        config: dict[str, Any],
        input_data: dict[str, Any] | None = None,
        runner_context: dict[str, Any] | None = None,
        subnode_configs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Executes a single node in isolation for testing."""
        runner = self.registry.get_runner(node_type)
        resolved_input = self._execute_subnodes_inline(
            input_data=input_data,
            subnode_configs=subnode_configs or [],
            runner_context=runner_context or {},
        )
        resolved_config = self._resolve_templates(
            config,
            self._build_template_context(resolved_input),
        )
        try:
            output_data = runner.run(
                config=resolved_config,
                input_data=resolved_input,
                context=runner_context or {},
            )
            return {
                "node_id": node_id,
                "node_type": node_type,
                "input_data": resolved_input,
                "output_data": output_data,
                "status": "SUCCEEDED",
                "error_message": None,
            }
        except Exception as exc:
            return {
                "node_id": node_id,
                "node_type": node_type,
                "input_data": resolved_input,
                "output_data": None,
                "status": "FAILED",
                "error_message": str(exc),
            }

    @staticmethod
    def _resolve_templates(
        config: dict[str, Any],
        input_data: Any,
    ) -> dict[str, Any]:
        """
        Resolve ``{{ ... }}`` expressions recursively in node config.

        Supported expression shapes (common n8n-like forms):
        - ``{{ field }}``
        - ``{{ nested.path }}``
        - ``{{ items[0].price }}``
        - ``{{ $json.field }}``
        - ``{{ $json["field"] }}``
        - ``{{ $node["node_id"].json.some.path }}``

        Behavior:
        - Whole-string placeholder keeps original type (dict/list/number/bool).
        - Embedded placeholder in larger text is stringified.
        - Unresolvable paths are preserved as-is.
        """
        _MISSING = object()
        _PATTERN = re.compile(r"\{\{\s*(.+?)\s*\}\}")

        def _normalize_expression(expression: str) -> str:
            expr = expression.strip()

            # n8n-ish node reference: $node["some_id"].json.path
            node_match = re.fullmatch(
                r"""\$node\[(["'])(.*?)\1\]\.json(.*)""",
                expr,
            )
            if node_match:
                node_id = node_match.group(2).strip()
                suffix = (node_match.group(3) or "").strip()
                expr = f"{node_id}{suffix}"

            # $json / json aliases for current payload
            if expr.startswith("$json"):
                expr = expr[len("$json") :]
            elif expr == "json" or expr.startswith("json.") or expr.startswith("json["):
                expr = expr[len("json") :]

            if expr.startswith("."):
                expr = expr[1:]

            return expr.strip()

        def _parse_path(path: str) -> list[str | int]:
            tokens: list[str | int] = []
            i = 0
            while i < len(path):
                ch = path[i]

                if ch == ".":
                    i += 1
                    continue

                if ch == "[":
                    i += 1
                    while i < len(path) and path[i].isspace():
                        i += 1
                    if i >= len(path):
                        break

                    if path[i] in {"'", '"'}:
                        quote = path[i]
                        i += 1
                        start = i
                        while i < len(path) and path[i] != quote:
                            if path[i] == "\\" and i + 1 < len(path):
                                i += 2
                            else:
                                i += 1
                        token = path[start:i]
                        i += 1 if i < len(path) else 0
                        while i < len(path) and path[i].isspace():
                            i += 1
                        if i < len(path) and path[i] == "]":
                            i += 1
                        tokens.append(token)
                        continue

                    start = i
                    while i < len(path) and path[i] != "]":
                        i += 1
                    raw = path[start:i].strip()
                    if i < len(path) and path[i] == "]":
                        i += 1

                    if not raw:
                        continue
                    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
                        tokens.append(int(raw))
                    else:
                        tokens.append(raw.strip("'\""))
                    continue

                start = i
                while i < len(path) and path[i] not in ".[":
                    i += 1
                token = path[start:i].strip()
                if token:
                    tokens.append(token)

            return tokens

        def _get(expression: str, data: Any) -> Any:
            normalized = _normalize_expression(expression)
            if normalized == "":
                return data

            tokens = _parse_path(normalized)
            if not tokens:
                return _MISSING

            current = data
            for token in tokens:
                if isinstance(token, int):
                    if isinstance(current, list) and -len(current) <= token < len(current):
                        current = current[token]
                    else:
                        return _MISSING
                    continue

                if isinstance(current, dict) and token in current:
                    current = current[token]
                    continue

                if isinstance(current, list) and token.isdigit():
                    index = int(token)
                    if -len(current) <= index < len(current):
                        current = current[index]
                        continue

                return _MISSING

            return current

        def _stringify(value: Any) -> str:
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            if value is None:
                return "null"
            return str(value)

        def _resolve(value: Any) -> Any:
            if isinstance(value, str):
                # Fast path: keep real type if the whole string is one expression.
                full = _PATTERN.fullmatch(value.strip())
                if full:
                    result = _get(full.group(1), input_data)
                    return value if result is _MISSING else result

                return _PATTERN.sub(
                    lambda m: (
                        m.group(0)
                        if (resolved := _get(m.group(1), input_data)) is _MISSING
                        else _stringify(resolved)
                    ),
                    value,
                )
            if isinstance(value, dict):
                return {k: _resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve(item) for item in value]
            return value

        return {k: _resolve(v) for k, v in config.items()}

    @staticmethod
    def _build_template_context(
        input_data: Any,
        node_outputs: dict[str, Any] | None = None,
    ) -> Any:
        template_context: dict[str, Any] = {}
        if isinstance(input_data, dict):
            template_context.update(input_data)
            payload_without_trigger_meta = {
                key: value
                for key, value in input_data.items()
                if key not in {"triggered", "trigger_type"}
            }

            # Keep n8n-like aliases available so both {{field}} and namespaced
            # forms such as {{form.field}} resolve from the same payload.
            for alias in ("form", "trigger", "manual", "schedule", "webhook", "workflow"):
                template_context.setdefault(alias, payload_without_trigger_meta)

            trigger_type = str(input_data.get("trigger_type") or "").strip().lower()
            if trigger_type in {"form", "manual", "schedule", "webhook", "workflow"}:
                template_context.setdefault(trigger_type, payload_without_trigger_meta)

        # Aliases for current upstream payload.
        template_context.setdefault("previous_output", input_data)
        template_context.setdefault("json", input_data)

        node_alias_context: dict[str, Any] = {}
        for node_id, output_data in (node_outputs or {}).items():
            template_context[node_id] = output_data
            node_alias_context[node_id] = {"json": output_data}

        template_context.setdefault("node", node_alias_context)
        return template_context

    @staticmethod
    def _inject_api_key(
        sub_output: Any,
        runner_context: dict[str, Any],
    ) -> Any:
        if not isinstance(sub_output, dict):
            return sub_output

        credential_id = sub_output.get("credential_id")
        if not credential_id or sub_output.get("api_key"):
            return sub_output

        resolved_credentials: dict[str, str] = (
            runner_context.get("resolved_credentials") or {}
        )
        api_key = resolved_credentials.get(str(credential_id))
        if not api_key:
            return sub_output

        return {
            **sub_output,
            "api_key": api_key,
        }

    def _execute_subnodes_inline(
        self,
        *,
        input_data: Any,
        subnode_configs: list[dict[str, Any]],
        runner_context: dict[str, Any],
        node_outputs: dict[str, Any] | None = None,
        exec_context: Any = None,
    ) -> Any:
        resolved_input = input_data

        for subnode in subnode_configs:
            sub_id = subnode.get("node_id")
            sub_type = subnode["node_type"]
            sub_handle = subnode.get("target_handle")
            sub_runner = self.registry.get_runner(sub_type)
            template_context = self._build_template_context(resolved_input, node_outputs)
            sub_config = self._resolve_templates(
                subnode.get("config", {}),
                template_context,
            )

            try:
                sub_output = sub_runner.run(
                    config=sub_config,
                    input_data=None,
                    context=runner_context,
                )
            except Exception as exc:
                if sub_id and exec_context is not None:
                    exec_context.node_states[sub_id] = "failed"
                raise ValueError(
                    f"Sub-node '{sub_id or sub_type}' ({sub_type}) failed: {exc}"
                ) from exc

            if sub_id and exec_context is not None:
                exec_context.node_states[sub_id] = "completed"
                exec_context.visited_nodes.append(sub_id)
                exec_context.node_outputs[sub_id] = sub_output

            if sub_handle:
                if not isinstance(resolved_input, dict):
                    resolved_input = {} if resolved_input is None else {"_default": resolved_input}
                resolved_input[sub_handle] = sub_output

        return resolved_input

    def build_context(self, definition: dict[str, Any]) -> ExecutionContext:
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])

        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise ValueError("Workflow definition must contain list fields: nodes and edges")

        nodes_by_id: dict[str, dict[str, Any]] = {}
        outgoing_edges: dict[str, list[dict[str, Any]]] = {}
        incoming_edges: dict[str, list[dict[str, Any]]] = {}
        indegree: dict[str, int] = {}

        for node in nodes:
            node_id = node.get("id")
            node_type = node.get("type")
            if not node_id:
                raise ValueError("Every node must have an id")
            if not node_type:
                raise ValueError(f"Node '{node_id}' must have a type")
            if node_id in nodes_by_id:
                raise ValueError(f"Duplicate node id found: {node_id}")

            nodes_by_id[node_id] = node
            outgoing_edges[node_id] = []
            incoming_edges[node_id] = []
            indegree[node_id] = 0

        subnode_edges: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes_by_id}
        loop_enabled, max_cycle_node_executions, max_total_node_executions = self._parse_loop_control(
            definition
        )

        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source not in nodes_by_id:
                raise ValueError(f"Edge source '{source}' does not exist")
            if target not in nodes_by_id:
                raise ValueError(f"Edge target '{target}' does not exist")

            source_type = nodes_by_id[source].get("type", "")
            if source_type in SUBNODE_TYPES:
                # Config sub-node: track separately, do NOT increment indegree
                subnode_edges[target].append(edge)
                continue

            if source_type == "if_else":
                branch_value = str(
                    edge.get("branch")
                    if edge.get("branch") is not None
                    else edge.get("sourceHandle") or ""
                ).strip()
                if branch_value not in {"true", "false"}:
                    raise ValueError(
                        f"if_else edge '{edge.get('id', source + '->' + target)}' must use branch 'true' or 'false'"
                    )
                edge["branch"] = branch_value
                edge["sourceHandle"] = branch_value

            if source_type == "switch":
                source_config = nodes_by_id[source].get("config", {})
                raw_cases = source_config.get("cases", []) if isinstance(source_config, dict) else []
                label_to_id: dict[str, str] = {}
                allowed_branches: set[str] = set()

                if isinstance(raw_cases, list):
                    for idx, case in enumerate(raw_cases):
                        if not isinstance(case, dict):
                            continue
                        case_id = str(case.get("id") or case.get("label") or f"case_{idx + 1}").strip()
                        case_label = str(case.get("label") or "").strip()
                        if case_id:
                            allowed_branches.add(case_id)
                        if case_label and case_id:
                            label_to_id[case_label] = case_id

                default_case = str(
                    source_config.get("default_case")
                    if isinstance(source_config, dict)
                    else "default"
                ).strip() or "default"
                allowed_branches.add(default_case)

                branch_value = str(
                    edge.get("branch")
                    if edge.get("branch") is not None
                    else edge.get("sourceHandle") or ""
                ).strip()
                if branch_value in label_to_id:
                    branch_value = label_to_id[branch_value]

                if branch_value not in allowed_branches:
                    raise ValueError(
                        "switch edge "
                        f"'{edge.get('id', source + '->' + target)}' has unknown branch '{branch_value}'"
                    )

                edge["branch"] = branch_value
                edge["sourceHandle"] = branch_value

            outgoing_edges[source].append(edge)
            incoming_edges[target].append(edge)
        cycle_node_ids: set[str] = set()
        cycle_edge_ids: set[str] = set()
        if loop_enabled:
            cycle_node_ids, cycle_edge_ids = self._identify_cycle_structure(
                nodes_by_id=nodes_by_id,
                outgoing_edges=outgoing_edges,
            )

            unsupported_cycle_nodes = [
                node_id
                for node_id in cycle_node_ids
                if nodes_by_id[node_id].get("type") in {"split_in", "split_out"}
            ]
            if unsupported_cycle_nodes:
                raise ValueError(
                    "Loop control currently does not support cycles that include split_in/split_out nodes: "
                    + ", ".join(sorted(unsupported_cycle_nodes))
                )

        for node_id in nodes_by_id:
            indegree[node_id] = 0
        for node_id, incoming in incoming_edges.items():
            indegree[node_id] = sum(
                1
                for edge in incoming
                if not (loop_enabled and self._edge_key(edge) in cycle_edge_ids)
            )

        if loop_enabled:
            pruned_outgoing_edges = {
                node_id: [
                    edge
                    for edge in node_edges
                    if self._edge_key(edge) not in cycle_edge_ids
                ]
                for node_id, node_edges in outgoing_edges.items()
            }
            topological_order = self._topological_sort(
                nodes_by_id,
                pruned_outgoing_edges,
                indegree,
            )
        else:
            topological_order = self._topological_sort(nodes_by_id, outgoing_edges, indegree)
        return ExecutionContext(
            definition=definition,
            nodes_by_id=nodes_by_id,
            outgoing_edges=outgoing_edges,
            incoming_edges=incoming_edges,
            subnode_edges=subnode_edges,
            indegree=indegree,
            topological_order=topological_order,
            node_states={node_id: "pending" for node_id in nodes_by_id},
            blocked_input_counts={node_id: 0 for node_id in nodes_by_id},
            pending_inputs={node_id: [] for node_id in nodes_by_id},
            split_buffers={node_id: [] for node_id in nodes_by_id},
            loop_enabled=loop_enabled,
            max_cycle_node_executions=max_cycle_node_executions,
            max_total_node_executions=max_total_node_executions,
            cycle_node_ids=cycle_node_ids,
            cycle_edge_ids=cycle_edge_ids,
            node_execution_counts={node_id: 0 for node_id in nodes_by_id},
        )

    @staticmethod
    def _edge_key(edge: dict[str, Any]) -> str:
        edge_id = edge.get("id")
        if edge_id is not None and str(edge_id).strip():
            return str(edge_id)
        return (
            f"{edge.get('source')}->{edge.get('target')}"
            f":{edge.get('branch')}:{edge.get('targetHandle')}"
        )

    @classmethod
    def _parse_loop_control(cls, definition: dict[str, Any]) -> tuple[bool, int, int]:
        raw = definition.get("loop_control")
        if not isinstance(raw, dict):
            raw = {}

        enabled = bool(raw.get("enabled", LOOP_CONTROL_DEFAULTS["enabled"]))
        max_node_raw = raw.get(
            "max_node_executions",
            LOOP_CONTROL_DEFAULTS["max_node_executions"],
        )
        max_total_raw = raw.get(
            "max_total_node_executions",
            LOOP_CONTROL_DEFAULTS["max_total_node_executions"],
        )

        try:
            max_node_executions = int(max_node_raw)
            max_total_node_executions = int(max_total_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "loop_control max_node_executions and max_total_node_executions must be integers"
            ) from exc

        if max_node_executions < 1:
            raise ValueError("loop_control.max_node_executions must be >= 1")
        if max_total_node_executions < 1:
            raise ValueError("loop_control.max_total_node_executions must be >= 1")

        return enabled, max_node_executions, max_total_node_executions

    @classmethod
    def _identify_cycle_structure(
        cls,
        *,
        nodes_by_id: dict[str, dict[str, Any]],
        outgoing_edges: dict[str, list[dict[str, Any]]],
    ) -> tuple[set[str], set[str]]:
        index = 0
        stack: list[str] = []
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        on_stack: set[str] = set()
        components: list[list[str]] = []

        def strong_connect(node_id: str) -> None:
            nonlocal index
            indices[node_id] = index
            lowlinks[node_id] = index
            index += 1
            stack.append(node_id)
            on_stack.add(node_id)

            for edge in outgoing_edges.get(node_id, []):
                target = edge["target"]
                if target not in indices:
                    strong_connect(target)
                    lowlinks[node_id] = min(lowlinks[node_id], lowlinks[target])
                elif target in on_stack:
                    lowlinks[node_id] = min(lowlinks[node_id], indices[target])

            if lowlinks[node_id] == indices[node_id]:
                component: list[str] = []
                while stack:
                    member = stack.pop()
                    on_stack.remove(member)
                    component.append(member)
                    if member == node_id:
                        break
                components.append(component)

        for node_id in nodes_by_id:
            if node_id not in indices:
                strong_connect(node_id)

        component_by_node: dict[str, int] = {}
        component_size: dict[int, int] = {}
        for idx, component in enumerate(components):
            component_size[idx] = len(component)
            for node_id in component:
                component_by_node[node_id] = idx

        cycle_node_ids: set[str] = set()
        cycle_edge_ids: set[str] = set()
        for source_id, edges in outgoing_edges.items():
            source_component = component_by_node.get(source_id)
            for edge in edges:
                target_id = edge["target"]
                target_component = component_by_node.get(target_id)
                if source_component is None or source_component != target_component:
                    continue
                same_component_size = component_size.get(source_component, 0)
                if same_component_size > 1 or source_id == target_id:
                    cycle_node_ids.add(source_id)
                    cycle_node_ids.add(target_id)
                    cycle_edge_ids.add(cls._edge_key(edge))

        return cycle_node_ids, cycle_edge_ids

    def _resolve_start_node(self, context: ExecutionContext) -> str:
        candidates = [
            node_id
            for node_id, node in context.nodes_by_id.items()
            if node["type"] in TRIGGER_NODE_TYPES and context.indegree[node_id] == 0
        ]
        if not candidates:
            raise ValueError("Workflow must contain one trigger node with indegree 0")
        if len(candidates) > 1:
            raise ValueError(
                "Workflow contains multiple trigger start nodes; pass start_node_id explicitly"
            )
        return candidates[0]

    def _topological_sort(
        self,
        nodes_by_id: dict[str, dict[str, Any]],
        outgoing_edges: dict[str, list[dict[str, Any]]],
        indegree: dict[str, int],
    ) -> list[str]:
        remaining_indegree = dict(indegree)
        queue = deque(
            node_id
            for node_id, degree in remaining_indegree.items()
            if degree == 0
        )
        ordered: list[str] = []

        while queue:
            node_id = queue.popleft()
            ordered.append(node_id)

            for edge in outgoing_edges[node_id]:
                target = edge["target"]
                remaining_indegree[target] -= 1
                if remaining_indegree[target] == 0:
                    queue.append(target)

        if len(ordered) != len(nodes_by_id):
            raise ValueError(
                "Workflow graph contains a cycle. Enable loop_control (or provide loop_control_override.enabled=true) to execute loop workflows."
            )

        return ordered

    def _execute_from_node(
        self,
        context: ExecutionContext,
        node_id: str,
        input_data: dict[str, Any] | None,
        target_handle: str | None = None,
    ) -> None:
        node = context.nodes_by_id[node_id]
        node_type = node["type"]
        is_cycle_node = node_id in context.cycle_node_ids

        if node_type in UNSUPPORTED_RUNTIME_NODE_TYPES:
            raise NotImplementedError(
                f"Node type '{node_type}' is not supported in this executor yet"
            )

        if (
            not is_cycle_node
            and context.node_states[node_id] in {"completed", "skipped"}
        ):
            return
        if is_cycle_node and context.node_states[node_id] == "skipped":
            return

        # Store input data mapped by handle
        merge_seed_payloads: list[Any] = []
        merge_seed_blocked_inputs = 0
        if (
            node_type == "merge"
            and isinstance(input_data, dict)
            and "__merge_inputs__" in input_data
        ):
            raw_merge_inputs = input_data.get("__merge_inputs__")
            if isinstance(raw_merge_inputs, list):
                merge_seed_payloads = list(raw_merge_inputs)
            raw_blocked = input_data.get("__merge_blocked_inputs__", 0)
            try:
                merge_seed_blocked_inputs = max(0, int(raw_blocked))
            except Exception:
                merge_seed_blocked_inputs = 0
            input_data = None

        if merge_seed_payloads:
            for payload in merge_seed_payloads:
                if (
                    isinstance(payload, dict)
                    and "data" in payload
                    and ("handle" in payload or "source_node_id" in payload)
                ):
                    context.pending_inputs[node_id].append(
                        {
                            "handle": payload.get("handle"),
                            "data": payload.get("data"),
                        }
                    )
                else:
                    context.pending_inputs[node_id].append(
                        {
                            "handle": None,
                            "data": payload,
                        }
                    )
            context.blocked_input_counts[node_id] = max(
                context.blocked_input_counts[node_id],
                merge_seed_blocked_inputs,
            )

        if input_data is not None:
            context.pending_inputs[node_id].append({
                "handle": target_handle,
                "data": input_data
            })

        # Check if node is ready (all non-blocked inputs received)
        accounted_inputs = (
            len(context.pending_inputs[node_id]) + context.blocked_input_counts[node_id]
        )
        if accounted_inputs < context.indegree[node_id] and context.indegree[node_id] > 0:
            return

        if context.total_node_executions >= context.max_total_node_executions:
            raise NodeExecutionError(
                node_id=node_id,
                node_type=node_type,
                input_data=input_data,
                original_exception=ValueError(
                    "Workflow stopped due to loop safety cap: "
                    f"max_total_node_executions={context.max_total_node_executions}"
                ),
            )

        if (
            is_cycle_node
            and context.node_execution_counts[node_id] >= context.max_cycle_node_executions
        ):
            context.pending_inputs[node_id] = []
            context.node_states[node_id] = "failed"
            cap_message = (
                "Loop safety cap reached for node "
                f"'{node_id}': max_node_executions={context.max_cycle_node_executions}"
            )
            self._emit_node_progress(
                node_id=node_id,
                node_type=node_type,
                status="FAILED",
                input_data=input_data,
                error_message=cap_message,
            )
            raise NodeExecutionError(
                node_id=node_id,
                node_type=node_type,
                input_data=input_data,
                original_exception=ValueError(cap_message),
            )

        # Special handling for nodes that might be triggered with NO inputs (triggers)
        # or nodes that are now ready.

        if node_type == "split_out":
            raise NotImplementedError(
                "split_out can only be executed as part of a split_in loop"
            )

        context.total_node_executions += 1
        context.node_execution_counts[node_id] += 1

        # Merge and SplitIn have their own specialized logic, but we've already 
        # collected their inputs. We'll adapt them.

        if node_type == "split_in":
            # split_in expects raw input_data from the first (and usually only) input
            raw_input = context.pending_inputs[node_id][0]["data"] if context.pending_inputs[node_id] else input_data
            context.pending_inputs[node_id] = []
            self._handle_split_in(context=context, node_id=node_id, input_data=raw_input)
            return

        # Prepare aggregated input for the runner
        # If there's only one input and no handle, pass it raw for backward compatibility.
        # Otherwise, pass a dict of handle -> data.
        
        all_inputs = context.pending_inputs[node_id]
        if not all_inputs:
            resolved_input = input_data
        elif len(all_inputs) == 1 and all_inputs[0]["handle"] is None:
            resolved_input = all_inputs[0]["data"]
        else:
            # Multi-input or handle-specific input
            resolved_input = {}
            for inp in all_inputs:
                handle = inp["handle"]
                data = inp["data"]
                if handle:
                    resolved_input[handle] = data
                else:
                    # Merge data for default handle or if no handle exists
                    if isinstance(data, dict):
                        resolved_input.update(data)
                    else:
                        resolved_input["_default"] = data

        if node_type == "merge":
            # Merge runner receives input envelopes so it can support handle-aware
            # two-input operations (n8n-like input_1/input_2 behavior).
            merge_data_list = list(all_inputs)
            context.pending_inputs[node_id] = []
            self._handle_merge_execution(context=context, node_id=node_id, merge_inputs=merge_data_list)
            return

        resolved_input = self._execute_subnodes_inline(
            input_data=resolved_input,
            subnode_configs=[
                {
                    "node_id": sub_edge["source"],
                    "node_type": context.nodes_by_id[sub_edge["source"]]["type"],
                    "target_handle": sub_edge.get("targetHandle"),
                    "config": context.nodes_by_id[sub_edge["source"]].get("config", {}),
                }
                for sub_edge in context.subnode_edges.get(node_id, [])
            ],
            runner_context=context.runner_context,
            node_outputs=context.node_outputs,
            exec_context=context,
        )

        runner = self.registry.get_runner(node_type)
        config = self._resolve_templates(
            node.get("config", {}),
            self._build_template_context(resolved_input, context.node_outputs),
        )
        context.node_inputs[node_id] = resolved_input
        self._emit_node_progress(
            node_id=node_id,
            node_type=node_type,
            status="RUNNING",
            input_data=resolved_input,
        )
        try:
            output_data = runner.run(config=config, input_data=resolved_input, context=context.runner_context)
        except Exception as exc:
            self._emit_node_progress(
                node_id=node_id,
                node_type=node_type,
                status="FAILED",
                input_data=resolved_input,
                error_message=str(exc),
            )
            raise NodeExecutionError(
                node_id=node_id,
                node_type=node_type,
                input_data=resolved_input,
                original_exception=exc,
            ) from exc
        
        output_data = self._preserve_internal_fields(
            node_type=node_type,
            input_data=resolved_input,
            output_data=output_data,
        )
        context.node_outputs[node_id] = output_data
        context.visited_nodes.append(node_id)
        context.node_states[node_id] = "completed"
        context.pending_inputs[node_id] = []
        self._emit_node_progress(
            node_id=node_id,
            node_type=node_type,
            status="SUCCEEDED",
            input_data=resolved_input,
            output_data=output_data,
        )

        selected_edges, blocked_edges = self._select_next_edges(
            node_type=node_type,
            output_data=output_data,
            outgoing_edges=context.outgoing_edges.get(node_id, []),
        )

        # For branching nodes, mark untaken paths immediately before traversing
        # selected paths so downstream joins (especially deferred merge resumes)
        # can observe skipped branches without a race.
        if node_type in BRANCHING_NODE_TYPES and blocked_edges:
            for edge in blocked_edges:
                self._block_path(context=context, node_id=edge["target"])
            blocked_edges = []

        next_input = self._strip_internal_fields(output_data)
        # Join-aware deferral:
        # If downstream target is a merge node, defer that edge into its own task
        # so merge input accounting can happen durably outside this in-memory context.
        if self._defer_callback is not None and node_type != "delay":
            deferred_merge_edges: list[dict[str, Any]] = []
            remaining_selected_edges: list[dict[str, Any]] = []
            for edge in selected_edges:
                target_node = context.nodes_by_id.get(edge.get("target"), {})
                if target_node.get("type") == "merge":
                    deferred_merge_edges.append(edge)
                else:
                    remaining_selected_edges.append(edge)

            for edge in deferred_merge_edges:
                self._defer_callback(
                    source_node_id=node_id,
                    source_node_type=node_type,
                    target_node_id=edge["target"],
                    target_handle=edge.get("targetHandle"),
                    payload=next_input,
                    delay_seconds=0.0,
                    delay_run_at=None,
                    loop_runtime_state=self._loop_runtime_state_snapshot(context=context),
                )

            selected_edges = remaining_selected_edges

        if (
            self._parallel_fanout_enabled
            and self._defer_callback is not None
            and len(selected_edges) > 1
            and self._can_parallelize_fanout(context=context, selected_edges=selected_edges)
        ):
            for edge in selected_edges:
                self._defer_callback(
                    source_node_id=node_id,
                    source_node_type=node_type,
                    target_node_id=edge["target"],
                    target_handle=edge.get("targetHandle"),
                    payload=next_input,
                    delay_seconds=0.0,
                    delay_run_at=None,
                    loop_runtime_state=self._loop_runtime_state_snapshot(context=context),
                )
            for edge in blocked_edges:
                self._block_path(context=context, node_id=edge["target"])
            return

        if node_type == "delay":
            delay_seconds = float(output_data.get("delay_seconds") or 0)
            if delay_seconds > 0 and selected_edges:
                delay_run_at = output_data.get("delay_run_at")
                for edge in selected_edges:
                    if self._defer_callback is not None:
                        self._defer_callback(
                            source_node_id=node_id,
                            source_node_type=node_type,
                            target_node_id=edge["target"],
                            target_handle=edge.get("targetHandle"),
                            payload=next_input,
                            delay_seconds=delay_seconds,
                            delay_run_at=delay_run_at,
                            loop_runtime_state=self._loop_runtime_state_snapshot(context=context),
                        )
                for edge in blocked_edges:
                    self._block_path(context=context, node_id=edge["target"])
                return

        for edge in selected_edges:
            self._execute_from_node(
                context=context,
                node_id=edge["target"],
                input_data=next_input,
                target_handle=edge.get("targetHandle")
            )

        for edge in blocked_edges:
            self._block_path(context=context, node_id=edge["target"])

    def _can_parallelize_fanout(
        self,
        *,
        context: ExecutionContext,
        selected_edges: list[dict[str, Any]],
    ) -> bool:
        # Only parallelize when branch paths are independent (no downstream joins).
        # If any reachable node has indegree > 1, keep existing in-process traversal.
        for edge in selected_edges:
            target_node_id = edge.get("target")
            if not target_node_id:
                return False
            if self._reachable_join_exists(context=context, start_node_id=target_node_id):
                return False
        return True

    @staticmethod
    def _reachable_join_exists(
        *,
        context: ExecutionContext,
        start_node_id: str,
    ) -> bool:
        queue = deque([start_node_id])
        seen: set[str] = set()

        while queue:
            node_id = queue.popleft()
            if node_id in seen:
                continue
            seen.add(node_id)

            if context.indegree.get(node_id, 0) > 1:
                return True

            for edge in context.outgoing_edges.get(node_id, []):
                next_node_id = edge.get("target")
                if next_node_id and next_node_id not in seen:
                    queue.append(next_node_id)

        return False

    def _handle_split_in(
        self,
        context: ExecutionContext,
        node_id: str,
        input_data: dict[str, Any] | None,
    ) -> None:
        runner = self.registry.get_runner("split_in")
        config = context.nodes_by_id[node_id].get("config", {})
        context.node_inputs[node_id] = input_data
        self._emit_node_progress(
            node_id=node_id,
            node_type="split_in",
            status="RUNNING",
            input_data=input_data,
        )
        try:
            split_outputs = runner.run(config=config, input_data=input_data)
        except Exception as exc:
            self._emit_node_progress(
                node_id=node_id,
                node_type="split_in",
                status="FAILED",
                input_data=input_data,
                error_message=str(exc),
            )
            raise NodeExecutionError(
                node_id=node_id,
                node_type="split_in",
                input_data=input_data,
                original_exception=exc,
            ) from exc
        context.node_outputs[node_id] = split_outputs
        context.visited_nodes.append(node_id)
        context.node_states[node_id] = "completed"
        self._emit_node_progress(
            node_id=node_id,
            node_type="split_in",
            status="SUCCEEDED",
            input_data=input_data,
            output_data=split_outputs,
        )

        split_out_node_id = self._resolve_split_out_node(context=context, split_in_node_id=node_id)
        context.split_buffers[split_out_node_id] = []

        for split_payload in split_outputs:
            for edge in context.outgoing_edges.get(node_id, []):
                self._execute_split_path(
                    context=context,
                    node_id=edge["target"],
                    input_data=split_payload,
                    split_out_node_id=split_out_node_id,
                )

        self._execute_split_out(
            context=context,
            node_id=split_out_node_id,
            collected_inputs=list(context.split_buffers[split_out_node_id]),
        )

    def _execute_split_path(
        self,
        context: ExecutionContext,
        node_id: str,
        input_data: dict[str, Any],
        split_out_node_id: str,
    ) -> None:
        if node_id == split_out_node_id:
            context.split_buffers[split_out_node_id].append(input_data)
            return

        node = context.nodes_by_id[node_id]
        node_type = node["type"]

        if node_type in {"merge", "split_in"}:
            raise NotImplementedError(
                f"Node type '{node_type}' is not supported inside split_in loops yet"
            )

        if node_type == "split_out":
            context.split_buffers[split_out_node_id].append(input_data)
            return

        runner = self.registry.get_runner(node_type)
        config = self._resolve_templates(
            node.get("config", {}),
            self._build_template_context(input_data, context.node_outputs),
        )
        context.node_inputs[node_id] = input_data
        self._emit_node_progress(
            node_id=node_id,
            node_type=node_type,
            status="RUNNING",
            input_data=input_data,
        )
        try:
            output_data = runner.run(config=config, input_data=input_data, context=context.runner_context)
        except Exception as exc:
            self._emit_node_progress(
                node_id=node_id,
                node_type=node_type,
                status="FAILED",
                input_data=input_data,
                error_message=str(exc),
            )
            raise NodeExecutionError(
                node_id=node_id,
                node_type=node_type,
                input_data=input_data,
                original_exception=exc,
            ) from exc
        output_data = self._preserve_internal_fields(
            node_type=node_type,
            input_data=input_data,
            output_data=output_data,
        )
        context.node_outputs[node_id] = output_data
        context.visited_nodes.append(node_id)
        context.node_states[node_id] = "completed"
        self._emit_node_progress(
            node_id=node_id,
            node_type=node_type,
            status="SUCCEEDED",
            input_data=input_data,
            output_data=output_data,
        )

        selected_edges, _blocked_edges = self._select_next_edges(
            node_type=node_type,
            output_data=output_data,
            outgoing_edges=context.outgoing_edges.get(node_id, []),
        )

        next_input = self._strip_internal_fields(output_data)
        for edge in selected_edges:
            self._execute_split_path(
                context=context,
                node_id=edge["target"],
                input_data=next_input,
                split_out_node_id=split_out_node_id,
            )

    def _execute_split_out(
        self,
        context: ExecutionContext,
        node_id: str,
        collected_inputs: list[dict[str, Any]],
    ) -> None:
        if context.node_states[node_id] == "completed":
            return

        runner = self.registry.get_runner("split_out")
        config = context.nodes_by_id[node_id].get("config", {})
        context.node_inputs[node_id] = collected_inputs
        self._emit_node_progress(
            node_id=node_id,
            node_type="split_out",
            status="RUNNING",
            input_data=collected_inputs,
        )
        try:
            output_data = runner.run(config=config, input_data=collected_inputs)
        except Exception as exc:
            self._emit_node_progress(
                node_id=node_id,
                node_type="split_out",
                status="FAILED",
                input_data=collected_inputs,
                error_message=str(exc),
            )
            raise NodeExecutionError(
                node_id=node_id,
                node_type="split_out",
                input_data=collected_inputs,
                original_exception=exc,
            ) from exc
        context.node_outputs[node_id] = output_data
        context.visited_nodes.append(node_id)
        context.node_states[node_id] = "completed"
        self._emit_node_progress(
            node_id=node_id,
            node_type="split_out",
            status="SUCCEEDED",
            input_data=collected_inputs,
            output_data=output_data,
        )

        next_input = self._strip_internal_fields(output_data)
        for edge in context.outgoing_edges.get(node_id, []):
            self._execute_from_node(
                context=context,
                node_id=edge["target"],
                input_data=next_input,
            )

    def _select_next_edges(
        self,
        node_type: str,
        output_data: dict[str, Any],
        outgoing_edges: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if node_type not in BRANCHING_NODE_TYPES:
            return outgoing_edges, []

        branch = output_data.get("_branch")
        if branch is None:
            raise ValueError(f"Branching node '{node_type}' did not return '_branch'")

        selected_edges = [
            edge for edge in outgoing_edges
            if edge.get("branch") == branch
        ]
        blocked_edges = [
            edge for edge in outgoing_edges
            if edge.get("branch") != branch
        ]
        return selected_edges, blocked_edges

    def _handle_merge_execution(
        self,
        context: ExecutionContext,
        node_id: str,
        merge_inputs: list[dict[str, Any]],
    ) -> None:
        runner = self.registry.get_runner("merge")
        config = context.nodes_by_id[node_id].get("config", {})
        merge_payloads = [
            inp.get("data")
            if isinstance(inp, dict) and "data" in inp and ("handle" in inp or "source_node_id" in inp)
            else inp
            for inp in merge_inputs
        ]
        context.node_inputs[node_id] = merge_payloads
        self._emit_node_progress(
            node_id=node_id,
            node_type="merge",
            status="RUNNING",
            input_data=merge_payloads,
        )
        try:
            output_data = runner.run(config=config, input_data=merge_inputs)
        except Exception as exc:
            self._emit_node_progress(
                node_id=node_id,
                node_type="merge",
                status="FAILED",
                input_data=merge_payloads,
                error_message=str(exc),
            )
            raise NodeExecutionError(
                node_id=node_id,
                node_type="merge",
                input_data=merge_payloads,
                original_exception=exc,
            ) from exc
        context.node_outputs[node_id] = output_data
        context.visited_nodes.append(node_id)
        context.node_states[node_id] = "completed"
        context.pending_inputs[node_id] = []
        self._emit_node_progress(
            node_id=node_id,
            node_type="merge",
            status="SUCCEEDED",
            input_data=merge_payloads,
            output_data=output_data,
        )

        next_input = self._strip_internal_fields(output_data)
        for edge in context.outgoing_edges.get(node_id, []):
            self._execute_from_node(
                context=context,
                node_id=edge["target"],
                input_data=next_input,
                target_handle=edge.get("targetHandle")
            )



    def _block_path(self, context: ExecutionContext, node_id: str) -> None:
        if (
            node_id not in context.cycle_node_ids
            and context.node_states[node_id] in {"completed", "skipped"}
        ):
            return
        if node_id in context.cycle_node_ids and context.node_states[node_id] == "skipped":
            return

        context.blocked_input_counts[node_id] += 1

        node_type = context.nodes_by_id[node_id]["type"]
        if node_type == "merge":
            accounted_inputs = (
                len(context.pending_inputs[node_id]) + context.blocked_input_counts[node_id]
            )
            if accounted_inputs < context.indegree[node_id]:
                # For merge nodes, an untaken branch is expected in conditional flows.
                # Keep merge in a waiting state instead of marking it as an error-like block.
                self._emit_node_progress(
                    node_id=node_id,
                    node_type=node_type,
                    status="WAITING",
                    error_message=None,
                )
                return
            if accounted_inputs == context.indegree[node_id]:
                if len(context.pending_inputs[node_id]) > 0:
                    merge_data_list = list(context.pending_inputs[node_id])
                    self._handle_merge_execution(context=context, node_id=node_id, merge_inputs=merge_data_list)
                else:
                    context.node_states[node_id] = "skipped"
                    self._emit_node_progress(
                        node_id=node_id,
                        node_type=node_type,
                        status="SKIPPED",
                        error_message="All incoming branches were blocked.",
                    )
                    for edge in context.outgoing_edges.get(node_id, []):
                        self._block_path(context=context, node_id=edge["target"])
            return

        accounted_inputs = (
            len(context.pending_inputs[node_id]) + context.blocked_input_counts[node_id]
        )
        if accounted_inputs < context.indegree[node_id]:
            self._emit_node_progress(
                node_id=node_id,
                node_type=node_type,
                status="BLOCKED",
                error_message="Waiting for remaining unblocked inputs.",
            )
            return

        if len(context.pending_inputs[node_id]) > 0:
            # A real input already arrived earlier. Once remaining paths are
            # accounted as blocked, run the node instead of leaving it blocked.
            self._execute_from_node(
                context=context,
                node_id=node_id,
                input_data=None,
                target_handle=None,
            )
            return

        context.node_states[node_id] = "skipped"
        self._emit_node_progress(
            node_id=node_id,
            node_type=node_type,
            status="SKIPPED",
            error_message="All incoming branches were blocked.",
        )
        for edge in context.outgoing_edges.get(node_id, []):
            self._block_path(context=context, node_id=edge["target"])

    def _resolve_split_out_node(
        self,
        context: ExecutionContext,
        split_in_node_id: str,
    ) -> str:
        queue = deque(edge["target"] for edge in context.outgoing_edges.get(split_in_node_id, []))
        seen: set[str] = set()
        split_out_candidates: list[str] = []

        while queue:
            node_id = queue.popleft()
            if node_id in seen:
                continue
            seen.add(node_id)

            node_type = context.nodes_by_id[node_id]["type"]
            if node_type == "split_in":
                raise NotImplementedError("Nested split_in loops are not supported yet")
            if node_type == "split_out":
                split_out_candidates.append(node_id)
                continue

            for edge in context.outgoing_edges.get(node_id, []):
                queue.append(edge["target"])

        if not split_out_candidates:
            raise ValueError(f"split_in node '{split_in_node_id}' does not lead to a split_out node")
        if len(split_out_candidates) > 1:
            raise NotImplementedError(
                f"split_in node '{split_in_node_id}' reaches multiple split_out nodes"
            )

        return split_out_candidates[0]

    @staticmethod
    def _strip_internal_fields(output_data: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in output_data.items()
            if key not in {"_branch"}
        }

    @staticmethod
    def _preserve_internal_fields(
        node_type: str,
        input_data: Any,
        output_data: Any,
    ) -> Any:
        if (
            node_type != "split_out"
            and isinstance(input_data, dict)
            and isinstance(output_data, dict)
            and "_split_index" in input_data
            and "_split_index" not in output_data
        ):
            return {
                **output_data,
                "_split_index": input_data["_split_index"],
            }

        return output_data

    def _emit_node_progress(
        self,
        *,
        node_id: str,
        node_type: str,
        status: str,
        input_data: Any = None,
        output_data: Any = None,
        error_message: str | None = None,
    ) -> None:
        if self._progress_callback is None:
            return
        try:
            self._progress_callback(
                node_id=node_id,
                node_type=node_type,
                status=status,
                input_data=input_data,
                output_data=output_data,
                error_message=error_message,
            )
        except WorkflowStopRequested:
            # Manual stop should abort execution quickly.
            raise
        except Exception:
            # Progress reporting must never fail workflow execution.
            return
