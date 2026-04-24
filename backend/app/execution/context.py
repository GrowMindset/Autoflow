from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionContext:
    """In-memory state for one dummy workflow run."""

    definition: dict[str, Any]
    nodes_by_id: dict[str, dict[str, Any]]
    outgoing_edges: dict[str, list[dict[str, Any]]]
    incoming_edges: dict[str, list[dict[str, Any]]]
    # subnode_edges: edges from config sub-nodes (chat_model_groq, chat_model_openai)
    # that are NOT counted toward indegree — they are resolved automatically inline
    # when the target node (e.g. ai_agent) is about to execute.
    subnode_edges: dict[str, list[dict[str, Any]]]
    indegree: dict[str, int]
    topological_order: list[str]
    node_inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    visited_nodes: list[str] = field(default_factory=list)
    node_states: dict[str, str] = field(default_factory=dict)
    blocked_input_counts: dict[str, int] = field(default_factory=dict)
    pending_inputs: dict[str, list[Any]] = field(default_factory=dict)
    split_buffers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    runner_context: dict[str, Any] = field(default_factory=dict)
    loop_enabled: bool = False
    max_cycle_node_executions: int = 3
    max_total_node_executions: int = 500
    cycle_node_ids: set[str] = field(default_factory=set)
    cycle_edge_ids: set[str] = field(default_factory=set)
    non_cycle_indegree: dict[str, int] = field(default_factory=dict)
    cycle_seeded_non_cycle_inputs: dict[str, int] = field(default_factory=dict)
    node_execution_counts: dict[str, int] = field(default_factory=dict)
    total_node_executions: int = 0
