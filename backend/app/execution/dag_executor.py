import json
import re
from collections import deque
from typing import Any, Callable

from app.execution.context import ExecutionContext
from app.execution.registry import RunnerRegistry


TRIGGER_NODE_TYPES = {"manual_trigger", "form_trigger", "webhook_trigger", "workflow_trigger"}
BRANCHING_NODE_TYPES = {"if_else", "switch"}
UNSUPPORTED_RUNTIME_NODE_TYPES = set()

# Sub-nodes are configuration helpers (e.g. Chat Model selectors) that attach to
# the *bottom* of a parent node via a named handle.  They are NOT part of the main
# data-flow and must NOT be counted toward the parent node's indegree.  Instead,
# the executor runs them automatically (inline) just before the parent executes,
# and injects their output into the parent's input under the targetHandle key.
SUBNODE_TYPES = {"chat_model_openai", "chat_model_groq"}


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


class DagExecutor:
    """Executes dummy workflow JSON in memory."""

    def __init__(self, registry: RunnerRegistry | None = None) -> None:
        self.registry = registry or RunnerRegistry()
        self._progress_callback: Callable[..., None] | None = None

    def execute(
        self,
        definition: dict[str, Any],
        initial_payload: dict[str, Any] | None = None,
        start_node_id: str | None = None,
        runner_context: dict[str, Any] | None = None,
        progress_callback: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        self._progress_callback = progress_callback
        context = self.build_context(definition)
        context.runner_context = runner_context or {}
        chosen_start_node_id = start_node_id or self._resolve_start_node(context)

        if chosen_start_node_id not in context.nodes_by_id:
            raise ValueError(f"Start node '{chosen_start_node_id}' was not found")

        start_node = context.nodes_by_id[chosen_start_node_id]
        if start_node["type"] not in TRIGGER_NODE_TYPES:
            raise ValueError(
                f"Start node '{chosen_start_node_id}' must be a trigger node"
            )

        try:
            self._execute_from_node(
                context=context,
                node_id=chosen_start_node_id,
                input_data=initial_payload,
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
            for alias in ("form", "trigger", "manual", "webhook", "workflow"):
                template_context.setdefault(alias, payload_without_trigger_meta)

            trigger_type = str(input_data.get("trigger_type") or "").strip().lower()
            if trigger_type in {"form", "manual", "webhook", "workflow"}:
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
            except Exception:
                sub_output = {}

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

            outgoing_edges[source].append(edge)
            incoming_edges[target].append(edge)
            indegree[target] += 1

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
        )

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
            raise ValueError("Workflow graph contains a cycle and is not a DAG")

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

        if node_type in UNSUPPORTED_RUNTIME_NODE_TYPES:
            raise NotImplementedError(
                f"Node type '{node_type}' is not supported in this executor yet"
            )

        if context.node_states[node_id] in {"completed", "skipped"}:
            return

        # Store input data mapped by handle
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

        # Special handling for nodes that might be triggered with NO inputs (triggers)
        # or nodes that are now ready.

        if node_type == "split_out":
            raise NotImplementedError(
                "split_out can only be executed as part of a split_in loop"
            )

        # Merge and SplitIn have their own specialized logic, but we've already 
        # collected their inputs. We'll adapt them.

        if node_type == "split_in":
            # split_in expects raw input_data from the first (and usually only) input
            raw_input = context.pending_inputs[node_id][0]["data"] if context.pending_inputs[node_id] else input_data
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
            # merge runner expects a list of inputs in context.pending_inputs
            # Our new logic already collected them, but merge runner expects just the data list
            merge_data_list = [inp["data"] for inp in all_inputs]
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

        next_input = self._strip_internal_fields(output_data)
        for edge in selected_edges:
            self._execute_from_node(
                context=context,
                node_id=edge["target"],
                input_data=next_input,
                target_handle=edge.get("targetHandle")
            )

        for edge in blocked_edges:
            self._block_path(context=context, node_id=edge["target"])

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
        context.node_inputs[node_id] = merge_inputs
        self._emit_node_progress(
            node_id=node_id,
            node_type="merge",
            status="RUNNING",
            input_data=merge_inputs,
        )
        try:
            output_data = runner.run(config=config, input_data=merge_inputs)
        except Exception as exc:
            self._emit_node_progress(
                node_id=node_id,
                node_type="merge",
                status="FAILED",
                input_data=merge_inputs,
                error_message=str(exc),
            )
            raise NodeExecutionError(
                node_id=node_id,
                node_type="merge",
                input_data=merge_inputs,
                original_exception=exc,
            ) from exc
        context.node_outputs[node_id] = output_data
        context.visited_nodes.append(node_id)
        context.node_states[node_id] = "completed"
        self._emit_node_progress(
            node_id=node_id,
            node_type="merge",
            status="SUCCEEDED",
            input_data=merge_inputs,
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
        if context.node_states[node_id] in {"completed", "skipped"}:
            return

        context.blocked_input_counts[node_id] += 1

        node_type = context.nodes_by_id[node_id]["type"]
        if node_type == "merge":
            accounted_inputs = (
                len(context.pending_inputs[node_id]) + context.blocked_input_counts[node_id]
            )
            if accounted_inputs == context.indegree[node_id]:
                if len(context.pending_inputs[node_id]) > 0:
                    merge_data_list = [inp["data"] for inp in context.pending_inputs[node_id]]
                    self._handle_merge_execution(context=context, node_id=node_id, merge_inputs=merge_data_list)
                else:
                    context.node_states[node_id] = "skipped"
                    for edge in context.outgoing_edges.get(node_id, []):
                        self._block_path(context=context, node_id=edge["target"])
            return

        if context.blocked_input_counts[node_id] < context.indegree[node_id]:
            return

        context.node_states[node_id] = "skipped"
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
        except Exception:
            # Progress reporting must never fail workflow execution.
            return
