# Integrations Folder

This folder contains third-party provider helpers and external service connectors.

Files that belong here:
- OAuth helper modules for Google and LinkedIn
- provider clients for OpenAI and future AI providers
- reusable wrappers for external APIs

Why this folder exists:
- To separate external API concerns from core business logic
- To make provider-specific code easier to swap or extend later
- To keep authentication and client setup for integrations in one place

Do not put here:
- route files
- SQLAlchemy models
- workflow execution orchestration

