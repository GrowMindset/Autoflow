"""Shared SQLAlchemy base classes and reusable column mixins.

This file centralizes the pieces that every model needs:
- `Base` is the declarative root SQLAlchemy uses to collect table metadata.
- `UUIDPrimaryKeyMixin` gives every table the agreed UUID primary key with
  PostgreSQL-side generation through `gen_random_uuid()`.
- `CreatedAtMixin` and `TimestampMixin` keep timestamp columns consistent and
  timezone-aware across the schema.
- `DEFAULT_WORKFLOW_DEFINITION` provides the default JSON structure for empty
  workflow canvases.

Keeping these pieces here avoids repeating the same column definitions in every
model and makes Alembic autogeneration more consistent.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func, text


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


DEFAULT_WORKFLOW_DEFINITION: dict[str, Any] = {
    "nodes": [],
    "edges": [],
    "loop_control": {
        "enabled": False,
        "max_node_executions": 3,
        "max_total_node_executions": 500,
    },
}


__all__ = [
    "Base",
    "CreatedAtMixin",
    "DEFAULT_WORKFLOW_DEFINITION",
    "JSONB",
    "PGUUID",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
]
