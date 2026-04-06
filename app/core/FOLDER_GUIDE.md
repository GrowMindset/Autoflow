# Core Folder

This folder contains shared application infrastructure used across the backend.

Files that belong here:
- `config.py` for environment variables and settings
- `database.py` for SQLAlchemy engine, session, and base setup
- `security.py` for password hashing and JWT utilities
- shared exceptions, constants, and middleware helpers

Why this folder exists:
- To centralize app-wide setup and cross-cutting concerns
- To avoid repeating config and security code in feature modules
- To keep foundational backend code easy to find

Do not put here:
- route handlers
- business workflows
- node runner implementations

