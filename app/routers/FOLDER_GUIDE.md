# Routers Folder

This folder contains FastAPI route modules.

Files that belong here:
- `auth.py` for signup, login, and current user routes
- `workflows.py` for workflow CRUD endpoints
- `executions.py` for run and status endpoints
- `ai.py` for workflow generation endpoints
- `credentials.py` and `webhooks.py` for integration-related APIs

Why this folder exists:
- To define the public API surface of the backend
- To keep endpoint declarations organized by feature
- To keep route handlers thin and delegate business work to services

Do not put here:
- heavy business logic
- direct external API orchestration
- complex DAG execution code

