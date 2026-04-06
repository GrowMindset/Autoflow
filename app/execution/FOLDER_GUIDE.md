# Execution Folder

This folder contains the workflow execution engine.

Files that belong here:
- `dag_executor.py` for topological sort and workflow execution flow
- `context.py` for execution context and node output tracking
- `registry.py` or runner mapping utilities
- `base_runner.py` for shared node runner contract
- `runners/` for node-specific execution logic

Why this folder exists:
- To isolate DAG execution from API and database layers
- To make node execution logic easier to test
- To support Phase 1 live nodes, Phase 2 AI node, and Phase 3 integrations cleanly

Do not put here:
- FastAPI routers
- ORM models
- frontend payload formatting unrelated to execution

