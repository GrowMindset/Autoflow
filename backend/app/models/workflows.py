"""Workflow definition model.

This file defines the `workflows` table, which stores one workflow per row.
Instead of splitting nodes and edges into separate tables, the full canvas is
stored in the `definition` JSONB column. That matches the agreed architecture
from the schema guide and keeps workflow saves simple.

The model also tracks publishing state and timestamps so the backend can
distinguish drafts from live workflows and sort by recent edits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.models.base import (
    Base,
    DEFAULT_WORKFLOW_DEFINITION,
    JSONB,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from app.models.executions import Execution
    from app.models.user import User
    from app.models.webhook import WebhookEndpoint
    from app.models.workflow_versions import WorkflowVersion


class Workflow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Workflow canvas definition owned by a single user."""

    __tablename__ = "workflows"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: DEFAULT_WORKFLOW_DEFINITION.copy(),
        server_default=text(
            '\'{"nodes": [], "edges": [], "loop_control": {"enabled": false, "max_node_executions": 3, "max_total_node_executions": 500}}\'::jsonb'
        ),
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    user: Mapped["User"] = relationship("User", back_populates="workflows")
    executions: Mapped[list["Execution"]] = relationship(
        "Execution", back_populates="workflow", cascade="all, delete-orphan"
    )
    webhook_endpoints: Mapped[list["WebhookEndpoint"]] = relationship(
        "WebhookEndpoint", back_populates="workflow", cascade="all, delete-orphan"
    )
    versions: Mapped[list["WorkflowVersion"]] = relationship(
        "WorkflowVersion", back_populates="workflow", cascade="all, delete-orphan"
    )
