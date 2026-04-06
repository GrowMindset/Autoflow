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

