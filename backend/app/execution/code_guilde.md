# DAG Execution Code Guide

This document explains how the code inside `backend/app/execution/` works today.

It is written for someone who wants to understand the current in-memory workflow engine before database, API, or background-task integration is added.

## Why This Folder Exists

The execution folder is responsible for one thing:

- take a workflow definition JSON
- validate it as a DAG
- execute nodes in the correct order
- route branches correctly
- handle merge and split behavior
- return execution results in memory

This folder is intentionally separate from:

- FastAPI routers
- SQLAlchemy models
- Celery tasks
- external integrations

That separation makes the engine easier to test and reason about.

## Current Files

### `dag_executor.py`

This is the main orchestration file.

It:

- builds the graph
- validates the graph with topological sort
- finds the start trigger
- executes nodes
- handles branching, merge, and split logic

If you want to understand the engine, start here.

### `context.py`

This stores the in-memory state for one workflow run.

Think of it as the execution scratchpad.

It keeps:

- graph lookup maps
- indegree information
- topo order
- latest node inputs and outputs
- visited node sequence
- node runtime states
- pending merge inputs
- split buffers

### `registry.py`

This maps node types to runner instances.

Instead of writing large `if node_type == ...` chains inside the executor, we ask the registry:

```python
runner = self.registry.get_runner(node_type)
```

That makes the executor much cleaner.

### `runners/nodes/`

This folder contains the node-specific transformation logic.

Examples:

- `filter`
- `if_else`
- `switch`
- `merge`
- `aggregate`
- `datetime_format`
- `split_in`
- `split_out`

These runners do not know about the whole graph.
They only know how to process their own input and config.

### `runners/triggers/`

This folder contains start-node runners:

- `manual_trigger`
- `form_trigger`
- `webhook_trigger`

These act like entry points for a workflow run.

### `demo_run.py`

This is a local demo helper.

It runs built-in sample workflows and prints the execution result JSON so you can inspect the engine behavior without API or DB wiring.

## Big Picture: How Execution Works

When you call:

```python
executor.execute(definition=workflow_json, initial_payload=payload)
```

the engine goes through these stages:

1. Build graph maps from `nodes` and `edges`
2. Calculate indegree for every node
3. Run topological sort to make sure the workflow is a DAG
4. Build an `ExecutionContext`
5. Find the start trigger node
6. Execute from that trigger node
7. Route through normal nodes, branch nodes, merge nodes, and split nodes
8. Return a summary of the in-memory run

## Step 1: Building the Graph

Inside `build_context()`, the executor reads:

- `definition["nodes"]`
- `definition["edges"]`

Then it builds:

- `nodes_by_id`
- `outgoing_edges`
- `incoming_edges`
- `indegree`

### Example

If the workflow is:

```json
{
  "nodes": [
    {"id": "n1", "type": "manual_trigger", "config": {}},
    {"id": "n2", "type": "filter", "config": {}}
  ],
  "edges": [
    {"id": "e1", "source": "n1", "target": "n2"}
  ]
}
```

then:

- `nodes_by_id["n1"]` gives the node object for `n1`
- `outgoing_edges["n1"]` gives the edge from `n1` to `n2`
- `incoming_edges["n2"]` gives the edge arriving at `n2`
- `indegree["n2"]` becomes `1`

This preprocessing makes execution fast because later code does not need to rescan the whole workflow JSON repeatedly.

## Step 2: Validating the DAG with Topological Sort

The engine uses Kahn's algorithm in `_topological_sort()`.

Why we do this:

- to confirm there is no cycle
- to compute a valid dependency order
- to support future execution features safely

### How it works

1. Copy the indegree map
2. Put all nodes with indegree `0` into a queue
3. Pop nodes one by one
4. Reduce indegree of their children
5. Add children whose indegree becomes `0`

If the final ordered list length is smaller than the total node count, the graph has a cycle.

Then the executor raises:

```python
ValueError("Workflow graph contains a cycle and is not a DAG")
```

## Step 3: Creating the Execution Context

After validation, the executor returns an `ExecutionContext`.

This object stores everything the run needs.

### Important fields

#### `node_inputs`

Latest input seen by each node id.

Important:
for split loops, this stores only the latest iteration input for that node.

#### `node_outputs`

Latest output seen by each node id.

Again, for repeated visits like split loops, this is last-write-wins.

#### `visited_nodes`

This preserves the execution sequence.

If a node runs multiple times, it appears multiple times here.

Example:

```json
["n1", "n2", "n3", "n3", "n3", "n4"]
```

This means `n3` ran three separate times.

#### `node_states`

Used to track whether a node is:

- `pending`
- `completed`
- `skipped`

This is especially important for merge and branch blocking.

#### `pending_inputs`

Used by merge nodes.

It stores incoming payloads until the merge is ready to execute.

#### `blocked_input_counts`

Also used by merge and branch handling.

When a branch is not taken, the executor marks downstream paths as blocked so merge nodes know that one parent path will never provide data.

#### `split_buffers`

Used by split loops.

It stores all iteration outputs that should later be passed into `split_out`.

## Step 4: Resolving the Start Node

The executor starts from a trigger node.

Current trigger types:

- `manual_trigger`
- `form_trigger`
- `webhook_trigger`

In `_resolve_start_node()` the engine finds a node that:

- is a trigger
- has indegree `0`

If there are multiple such nodes, the caller must pass `start_node_id`.

This prevents ambiguity.

## Step 5: Normal Node Execution

Normal execution happens inside `_execute_from_node()`.

The basic flow is:

1. Find the node from `context.nodes_by_id`
2. Read its type
3. Get the runner from `RunnerRegistry`
4. Call `runner.run(config, input_data)`
5. Save input and output in context
6. Mark the node as visited
7. Move to downstream nodes

### Example

For a `filter` node:

- executor passes the node config and input payload to `FilterRunner`
- runner returns filtered data
- executor stores the result
- executor forwards that result to the next node

This is the standard pattern for most nodes.

## Step 6: Trigger Nodes

Trigger nodes are just special start nodes.

Their runners return metadata plus payload.

Example manual trigger output:

```json
{
  "triggered": true,
  "trigger_type": "manual",
  "...payload": "..."
}
```

This is why downstream nodes often still see trigger metadata unless a later node replaces the payload shape.

## Step 7: Branching with `if_else` and `switch`

Branching nodes are:

- `if_else`
- `switch`

These runners return a normal payload plus an internal `_branch` field.

Example:

```json
{
  "status": "paid",
  "_branch": "true"
}
```

The executor then:

1. reads `_branch`
2. selects only edges whose `branch` value matches
3. marks all non-selected edges as blocked
4. removes `_branch` before sending data forward

That routing logic lives in `_select_next_edges()` and `_block_path()`.

### Why `_block_path()` matters

Suppose a branch has two outgoing paths but only one is taken.

The untaken path must be marked as blocked so:

- merge nodes know not to wait forever
- downstream nodes can be marked skipped if all their inputs are blocked

Without this, fan-in behavior would break.

## Step 8: Merge Nodes

Merge is handled specially in `_handle_merge_input()`.

The merge runner expects a list of parent outputs, so the executor cannot run merge immediately after the first parent arrives.

Instead it:

1. stores incoming payloads in `pending_inputs[node_id]`
2. checks whether all parent paths are accounted for
3. if yes, runs `MergeRunner`

### What "accounted for" means

For a merge node, every incoming edge must end up in one of two states:

- produced a real payload
- was blocked because the branch path was not taken

This check is done by `_is_merge_ready()`.

### Example

If merge has indegree `2`:

- one path delivers data
- one path is blocked

then merge is still allowed to run, because all incoming paths are accounted for.

That is how branch reconvergence works.

## Step 9: Split Loops with `split_in` and `split_out`

Split handling is the most custom part of the executor.

### `split_in`

`SplitInRunner` returns a list of iteration payloads:

```json
[
  {"item": {...}, "_split_index": 0},
  {"item": {...}, "_split_index": 1}
]
```

The executor does not simply forward this list as one payload.

Instead `_handle_split_in()`:

1. runs `split_in`
2. finds the matching `split_out` node by scanning downstream
3. executes the loop body once per split payload
4. collects results into `split_buffers`
5. runs `split_out` one time at the end

### Why `_split_index` matters

Each iteration gets `_split_index`.

The executor preserves it through intermediate loop nodes using `_preserve_internal_fields()`.

That allows `split_out` to rebuild results in original order.

### `_execute_split_path()`

This is the recursive loop-body executor.

It behaves similarly to `_execute_from_node()`, but with one key difference:

- when it reaches the target `split_out`, it does not execute it immediately
- it pushes the current iteration payload into `split_buffers`

Only after all iterations are done does `_execute_split_out()` run.

### `_resolve_split_out_node()`

The executor finds the matching `split_out` by traversing downstream nodes from the `split_in`.

Current rules:

- nested `split_in` is not supported
- multiple reachable `split_out` nodes are not supported
- `split_in` must eventually lead to one `split_out`

These rules keep the first implementation manageable.

## Step 10: Internal Fields

Two internal fields are important:

### `_branch`

Used only for branch routing.

The executor strips it before normal downstream execution.

### `_split_index`

Used only for split loop ordering.

The executor preserves it across loop-body nodes and `split_out` strips it when assembling final results.

This logic lives in:

- `_strip_internal_fields()`
- `_preserve_internal_fields()`

## Step 11: What `execute()` Returns

At the end, `execute()` returns a dict with:

- `topological_order`
- `visited_nodes`
- `node_inputs`
- `node_outputs`
- `terminal_outputs`

### Important limitation

For nodes that run multiple times, like a node inside a split loop:

- `visited_nodes` keeps all visits
- `node_inputs[node_id]` stores only the latest input
- `node_outputs[node_id]` stores only the latest output

So the engine is correct, but the debug trace is simplified.

If full per-visit history is needed later, we should add a dedicated execution log list instead of only `node_id -> latest value`.

## Current Supported Behavior

Today the executor supports:

- graph validation with indegree + topological sort
- trigger start nodes
- linear execution
- `if_else`
- `switch`
- `merge`
- `split_in`
- `split_out`

## Engine Limitations

These are important to know before extending the in-memory engine:

- split-loop nodes overwrite `node_inputs` and `node_outputs` for repeated visits
- nested `split_in` loops are not supported
- multiple `split_out` targets from one split loop are not supported
- `merge` inside a split loop is not supported yet
- `split_in` inside another split loop is not supported yet
- direct standalone execution of `split_out` is not allowed

## Integration with Database and Tasks

*(Note: The limitations about no DB, no API, and no Celery have been resolved.)*

While the `execution/` folder focuses purely on **in-memory** evaluation of the DAG:
- **API & Routing** is handled by FastApi routers in `backend/app/routers/`.
- **Database Persistence** (saving `Execution` and `NodeExecution` rows) and **Job Dispatching** is handled by `backend/app/services/` (e.g., `ExecutionService`).
- **Background Execution** is handled by Celery in `backend/app/tasks/execute_workflow.py`. The Celery workers load the DB state, run the `DagExecutor` (or single `execute_node`), and update the status rows back to the database in real-time.

## Recommended Reading Order for New Developers

If you are reading this code for the first time, use this order:

1. `backend/app/services/code_guide.md` (Explains integration)
2. `backend/app/execution/demo_run.py`
3. `backend/app/execution/dag_executor.py`
4. `backend/app/execution/context.py`
5. `backend/app/execution/registry.py`
6. `backend/app/execution/runners/triggers/`
7. `backend/app/execution/runners/nodes/`
8. `backend/test/test_dag_executor.py`

This order is best because:

- `code_guide.md` in services shows how everything hooks up at a high level
- `demo_run.py` shows how the engine is called
- `dag_executor.py` shows the runtime flow
- `context.py` explains the stored state
- `registry.py` explains runner resolution
- runners show node-level behavior
- tests show expected outcomes

## Mental Model to Remember

The easiest way to think about this code is:

- runners know how to transform data
- the registry knows how to find runners
- the context remembers everything about the current run
- the executor decides where data flows next

So:

- runner = "what does this node do?"
- executor = "where does execution go now?"

That separation is the main architectural idea behind this folder.
