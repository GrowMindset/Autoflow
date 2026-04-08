from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionContext:
    """In-memory state for one dummy workflow run."""

    definition: dict[str, Any]
    nodes_by_id: dict[str, dict[str, Any]]
    outgoing_edges: dict[str, list[dict[str, Any]]]
    incoming_edges: dict[str, list[dict[str, Any]]]
    indegree: dict[str, int]
    topological_order: list[str]
    node_inputs: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)
    visited_nodes: list[str] = field(default_factory=list)
    node_states: dict[str, str] = field(default_factory=dict)
    blocked_input_counts: dict[str, int] = field(default_factory=dict)
    pending_inputs: dict[str, list[Any]] = field(default_factory=dict)
    split_buffers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
