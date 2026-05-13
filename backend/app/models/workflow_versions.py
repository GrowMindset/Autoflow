"""Immutable workflow snapshots for manual version history.

Each row stores one version snapshot for a workflow. Snapshots are created
explicitly by the user (manual save + version), not by autosave.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, JSONB, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.workflows import Workflow


class WorkflowVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable snapshot row for a workflow definition at a point in time."""

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "version_number",
            name="uq_workflow_versions_workflow_id_version_number",
        ),
    )

    workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="versions")
