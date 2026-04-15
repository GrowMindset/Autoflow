# Tasks Folder

This folder contains Celery task definitions and background job entry points.

Files that belong here:
- `execute_workflow.py` for the main workflow execution background task
- helper task modules for asynchronous processing if needed later

Why this folder exists:
- To separate background job triggers from synchronous API requests
- To keep Celery-related code grouped together
- To support queued workflow execution with Redis cleanly

Do not put here:
- route handlers
- direct database model definitions
- provider-specific API helper code

## Worker topology (recommended)

- Queue `workflow.executions`: full workflow runs
- Queue `workflow.node_tests`: node test runs
- Queue `system`: small internal tasks

Run workers in separate terminals/processes for better throughput:

```bash
celery -A celery_config worker -l info -n wf1@%h -Q workflow.executions,celery -c 4
celery -A celery_config worker -l info -n wf2@%h -Q workflow.executions,celery -c 4
celery -A celery_config worker -l info -n node@%h -Q workflow.node_tests,celery -c 2
```

This avoids node-test jobs starving full workflow executions and scales horizontally.
