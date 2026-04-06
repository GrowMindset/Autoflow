# Models Folder

This folder contains SQLAlchemy ORM models for database tables.

Files that belong here:
- one model file per table such as `user.py`, `workflow.py`, and `execution.py`
- shared ORM base model file if needed
- table relationships and database column definitions

Why this folder exists:
- To define the database schema in Python code
- To keep persistence models separate from API schemas
- To make migrations and database operations easier to manage

Do not put here:
- Pydantic request or response schemas
- endpoint logic
- Celery tasks

