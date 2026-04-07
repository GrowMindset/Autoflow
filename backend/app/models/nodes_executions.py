"""Per-node execution result model.

This file defines the `node_executions` table. Each row captures what happened
for one node during one workflow run, including the node identifier from the
workflow definition, current status, input payload, output payload, and any
node-specific error.

This table is especially important for debugging and for frontend features such
as node coloring and the side panel that shows node inputs and outputs.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.models.base import Base, JSONB, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.executions import Execution


class NodeExecution(UUIDPrimaryKeyMixin, Base):
    """Execution result for one workflow node within a workflow run."""

    __tablename__ = "node_executions"

    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(50), nullable=False)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    execution: Mapped["Execution"] = relationship("Execution", back_populates="node_executions")
