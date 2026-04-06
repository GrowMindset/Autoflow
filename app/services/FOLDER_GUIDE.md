# Services Folder

This folder contains business logic used by the API layer.

Files that belong here:
- `auth_service.py` for signup and login logic
- `workflow_service.py` for workflow CRUD operations
- `execution_service.py` for run orchestration and status retrieval
- `ai_service.py` for workflow generation or AI-related backend logic
- `webhook_service.py` and `credential_service.py` for supporting modules

Why this folder exists:
- To keep routers simple and focused on HTTP concerns
- To centralize reusable application logic
- To make core backend behavior easier to test without the API layer

Do not put here:
- raw route definitions
- ORM model declarations
- node runner implementations

