# Services & Execution Flow Code Guide

This document explains the role of the `backend/app/services/` directory and how the application triggers and processes workflow executions, including the detailed interaction with Celery workers.

## Why This Folder Exists

The `services` folder acts as the integration layer (the "controller" or "use-case" layer) between:
1. **FastAPI Routers** (HTTP requests)
2. **Database Models** (SQLAlchemy persistence)
3. **Execution Engine** (`app.execution` logic)
4. **Background Tasks** (Celery queueing)

By keeping this logic in `services/`, our API routers remain thin, and our data models remain decoupled from complex execution orchestration.

## Key Files

### `workflow_service.py`
Revolves around the lifecycle of a `Workflow` blueprint itself.
- **CRUD Operations**: Creation, listing, fetching, updating, and deleting workflows.
- **Webhook Management**: When a workflow containing a `webhook_trigger` is published, this service automatically generates and persists a `WebhookEndpoint` with a unique `path_token`. If unpublished, it marks the endpoint as inactive.

### `execution_service.py`
Revolves around the lifecycle of an `Execution` run and its child `NodeExecution` pieces. This is the main bridge to start a flow.
- **Trigger Methods**: Can create executions for manual triggers, form triggers, webhooks, or isolated single-node tests (`create_node_test_execution`).
- **Database Prep**: It spins up an `Execution` row with a `PENDING` status. Critically, it also pre-creates `NodeExecution` rows for every node mapped in the workflow so the UI knows exactly what to expect before processing even starts.
- **Job Dispatch**: After creating the rows, it invokes `.delay()` on the Celery task (e.g., `run_execution.delay(...)` or `run_node_test.delay(...)`). This puts the actual heavy-lifting work onto the background broker message queue.

---

## Deep Dive: How Celery Workers Process Jobs

When the user clicks "Run" or a webhook is triggered, the FastAPI response returns almost immediately. The actual execution runs entirely via a **Celery worker**. Here is the step-by-step breakdown:

### 1. Enqueueing Jobs (`.delay()`)
From `execution_service.py`, a task is queued:
```python
run_execution.delay(
    execution_id=str(execution.id),
    initial_payload=initial_payload,
    start_node_id=start_node_id,
)
```
Celery translates this function call into a serialized message pushed to the broker (typically Redis). 

### 2. The Worker Checks Out the Job
A background node running the Celery worker (e.g. `celery -A celery_config worker`) constantly listens to the broker queue. When it grabs the queued message, it reconstructs it and begins executing the python function defined in `backend/app/tasks/execute_workflow.py`.

### 3. Inside Worker Execution (`execute_workflow.py`)
Since FastAPI heavily leverages `async/await` and SQLAlchemy's `AsyncSession`, but Celery prefers synchronous task wrappers, the task function `run_execution` utilizes `asyncio.run(_run_execution(...))` to kick off an embedded async loop.

Inside `_run_execution`:
1. **DB Setup**: The worker connects to the database, pulling a session specifically made for the task `_create_task_session_factory()`.
2. **Load Database State**: It fetches the overall `Execution` row and the `Workflow` JSON definition block.
3. **Mark as Running**: It updates the status of the `Execution` and `NodeExecutions` to `RUNNING` or `PENDING` and stamps the `started_at` time.
4. **Invoke the In-Memory Engine**: The worker hands the payload to the pure Python in-memory graph processor from `execution/dag_executor.py`:
   ```python
   result = DagExecutor().execute(
       definition=workflow.definition,
       initial_payload=initial_payload,
       start_node_id=start_node_id,
   )
   ```
   **Core Concept**: The executor is synchronous and lives entirely in memory. It *does not* hit the DB. It simply moves inputs from node to node, processing data.
5. **Persist the In-Memory Results to DB**: Because `DagExecutor` returns a consolidated `result` dict containing `visited_nodes`, `node_inputs`, and `node_outputs`, the worker maps these back. Loop through nodes:
   - If bounded in `visited_nodes`, mark as `SUCCEEDED`, map `node_inputs` / `node_outputs`, and timestamp `finished_at`.
6. **Completion / Failure Check**: 
   - If successful, the entire `Execution` finishes smoothly as `SUCCEEDED`.
   - If a specific runner failed, `DagExecutor` raises a `NodeExecutionError`. The worker catches this natively, finds exactly which node crashed in the execution table, dumps the stack trace/error into `error_message`, sets `FAILED`, and bubbles the failure to the main `Execution`.
   
### 4. Single Node Testing (`run_node_test`)
A very identical flow exists for validating a single graph node in isolation. A request is made to test the node, the `ExecutionService` pushes a lightweight execution row containing just that single node to Celery, and the worker spins up just that one node instance (`DagExecutor().execute_node()`). The exact result feeds back live in the UI.

### Architecture Summary
- **FastAPI / Service** handles the **"what"** and **"when"** (Validates request, writes DB pending rows, tells Celery queue to start).
- **Celery Worker / Task** handles the **"how"** and **"safety"** (Pulls from queue, orchestrates DB and DAG logic, handles crashes gracefully so APIs don't hang).
- **Execution Engine** handles the **"core graph logic"** (A pure, uncoupled, readily testable python engine transforming objects between nodes).
