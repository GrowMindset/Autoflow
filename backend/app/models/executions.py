"""Workflow execution model.

This file defines the `executions` table, where each row represents one run of a
workflow. Runs are historical records and are not reused for later executions.
The table links a run back to both the workflow and the user who triggered it,
and stores high-level lifecycle data such as status, start time, finish time,
and execution-level errors.

Detailed per-node results live in `node_executions`, which connect back to an
execution through the relationship defined here.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.nodes_executions import NodeExecution
    from app.models.user import User
    from app.models.workflows import Workflow


class Execution(UUIDPrimaryKeyMixin, Base):
    """Immutable record of a single workflow run."""

    __tablename__ = "executions"

    workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="executions")
    user: Mapped["User"] = relationship("User", back_populates="executions")
    node_executions: Mapped[list["NodeExecution"]] = relationship(
        "NodeExecution", back_populates="execution", cascade="all, delete-orphan"
    )
