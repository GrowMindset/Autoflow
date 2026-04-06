# Alembic Folder

This folder contains database migration setup and version history.

Files that belong here:
- `env.py` for Alembic environment and database connection wiring
- `script.py.mako` for migration file template
- `versions/` files for generated migration scripts

Why this folder exists:
- To track database schema changes over time
- To let the team upgrade or rollback the PostgreSQL schema safely
- To keep schema evolution separate from application business logic

Do not put here:
- SQLAlchemy models
- API routes
- service logic

