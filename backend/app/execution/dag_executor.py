from collections import deque
from typing import Any

from app.execution.context import ExecutionContext
from app.execution.registry import RunnerRegistry


TRIGGER_NODE_TYPES = {"manual_trigger", "form_trigger", "webhook_trigger", "workflow_trigger"}
BRANCHING_NODE_TYPES = {"if_else", "switch"}
UNSUPPORTED_RUNTIME_NODE_TYPES = set()


class NodeExecutionError(Exception):
    def __init__(
        self,
        *,
        node_id: str,
        node_type: str,
        input_data: Any,
        original_exception: Exception,
    ) -> None:
        self.node_id = node_id
        self.node_type = node_type
        self.input_data = input_data
        self.original_exception = original_exception
        super().__init__(str(original_exception))


class DagExecutor:
    """Executes dummy workflow JSON in memory."""

    def __init__(self, registry: RunnerRegistry | None = None) -> None:
        self.registry = registry or RunnerRegistry()

    def execute(
        self,
        definition: dict[str, Any],
        initial_payload: dict[str, Any] | None = None,
        start_node_id: str | None = None,
    ) -> dict[str, Any]:
        context = self.build_context(definition)
        chosen_start_node_id = start_node_id or self._resolve_start_node(context)

        if chosen_start_node_id not in context.nodes_by_id:
            raise ValueError(f"Start node '{chosen_start_node_id}' was not found")

        start_node = context.nodes_by_id[chosen_start_node_id]
        if start_node["type"] not in TRIGGER_NODE_TYPES:
            raise ValueError(
                f"Start node '{chosen_start_node_id}' must be a trigger node"
            )

        self._execute_from_node(
            context=context,
            node_id=chosen_start_node_id,
            input_data=initial_payload,
        )

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
    ) -> dict[str, Any]:
        """Executes a single node in isolation for testing."""
        runner = self.registry.get_runner(node_type)
        try:
            output_data = runner.run(config=config, input_data=input_data)
            return {
                "node_id": node_id,
                "node_type": node_type,
                "input_data": input_data,
                "output_data": output_data,
                "status": "SUCCEEDED",
                "error_message": None,
            }
        except Exception as exc:
            return {
                "node_id": node_id,
                "node_type": node_type,
                "input_data": input_data,
                "output_data": None,
                "status": "FAILED",
                "error_message": str(exc),
            }

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

        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source not in nodes_by_id:
                raise ValueError(f"Edge source '{source}' does not exist")
            if target not in nodes_by_id:
                raise ValueError(f"Edge target '{target}' does not exist")

            outgoing_edges[source].append(edge)
            incoming_edges[target].append(edge)
            indegree[target] += 1

        topological_order = self._topological_sort(nodes_by_id, outgoing_edges, indegree)
        return ExecutionContext(
            definition=definition,
            nodes_by_id=nodes_by_id,
            outgoing_edges=outgoing_edges,
            incoming_edges=incoming_edges,
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
    ) -> None:
        node = context.nodes_by_id[node_id]
        node_type = node["type"]

        if node_type in UNSUPPORTED_RUNTIME_NODE_TYPES:
            raise NotImplementedError(
                f"Node type '{node_type}' is not supported in this executor yet"
            )

        if context.node_states[node_id] in {"completed", "skipped"}:
            return

        if node_type == "split_out":
            raise NotImplementedError(
                "split_out can only be executed as part of a split_in loop"
            )

        if node_type == "merge":
            self._handle_merge_input(context=context, node_id=node_id, input_data=input_data)
            return

        if node_type == "split_in":
            self._handle_split_in(context=context, node_id=node_id, input_data=input_data)
            return

        runner = self.registry.get_runner(node_type)
        config = node.get("config", {})
        context.node_inputs[node_id] = input_data
        try:
            output_data = runner.run(config=config, input_data=input_data)
        except Exception as exc:
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
        try:
            split_outputs = runner.run(config=config, input_data=input_data)
        except Exception as exc:
            raise NodeExecutionError(
                node_id=node_id,
                node_type="split_in",
                input_data=input_data,
                original_exception=exc,
            ) from exc
        context.node_outputs[node_id] = split_outputs
        context.visited_nodes.append(node_id)
        context.node_states[node_id] = "completed"

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
        config = node.get("config", {})
        context.node_inputs[node_id] = input_data
        try:
            output_data = runner.run(config=config, input_data=input_data)
        except Exception as exc:
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
        try:
            output_data = runner.run(config=config, input_data=collected_inputs)
        except Exception as exc:
            raise NodeExecutionError(
                node_id=node_id,
                node_type="split_out",
                input_data=collected_inputs,
                original_exception=exc,
            ) from exc
        context.node_outputs[node_id] = output_data
        context.visited_nodes.append(node_id)
        context.node_states[node_id] = "completed"

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

    def _handle_merge_input(
        self,
        context: ExecutionContext,
        node_id: str,
        input_data: dict[str, Any] | None,
    ) -> None:
        if input_data is not None:
            context.pending_inputs[node_id].append(input_data)

        if not self._is_merge_ready(context=context, node_id=node_id):
            return

        runner = self.registry.get_runner("merge")
        config = context.nodes_by_id[node_id].get("config", {})
        merge_inputs = list(context.pending_inputs[node_id])
        context.node_inputs[node_id] = merge_inputs
        try:
            output_data = runner.run(config=config, input_data=merge_inputs)
        except Exception as exc:
            raise NodeExecutionError(
                node_id=node_id,
                node_type="merge",
                input_data=merge_inputs,
                original_exception=exc,
            ) from exc
        context.node_outputs[node_id] = output_data
        context.visited_nodes.append(node_id)
        context.node_states[node_id] = "completed"

        next_input = self._strip_internal_fields(output_data)
        for edge in context.outgoing_edges.get(node_id, []):
            self._execute_from_node(
                context=context,
                node_id=edge["target"],
                input_data=next_input,
            )

    def _is_merge_ready(self, context: ExecutionContext, node_id: str) -> bool:
        accounted_inputs = (
            len(context.pending_inputs[node_id]) + context.blocked_input_counts[node_id]
        )
        return (
            context.node_states[node_id] == "pending"
            and accounted_inputs == context.indegree[node_id]
            and len(context.pending_inputs[node_id]) > 0
        )

    def _block_path(self, context: ExecutionContext, node_id: str) -> None:
        if context.node_states[node_id] in {"completed", "skipped"}:
            return

        context.blocked_input_counts[node_id] += 1

        node_type = context.nodes_by_id[node_id]["type"]
        if node_type == "merge":
            if self._is_merge_ready(context=context, node_id=node_id):
                self._handle_merge_input(context=context, node_id=node_id, input_data=None)
            elif context.blocked_input_counts[node_id] == context.indegree[node_id]:
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
