# Schemas Folder

This folder contains Pydantic models for request validation and response serialization.

Files that belong here:
- request and response schemas for auth, workflows, executions, credentials, and AI
- shared enums or helper schema models when needed

Why this folder exists:
- To validate incoming API payloads
- To standardize outgoing response shapes
- To separate transport models from database models

Do not put here:
- SQLAlchemy ORM classes
- route logic
- business services

