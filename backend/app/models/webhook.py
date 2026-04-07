"""Webhook endpoint registration model.

This file defines the `webhook_endpoints` table, which maps a generated public
path token to a specific workflow and webhook trigger node. It allows external
systems to trigger workflows through a stable URL without exposing internal
workflow identifiers.

The stored token is unique and intended to remain immutable once created, which
matches the integration requirements documented in the schema guide.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workflows import Workflow


class WebhookEndpoint(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Public webhook registration that maps an incoming request to a workflow node."""

    __tablename__ = "webhook_endpoints"

    workflow_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(50), nullable=False)
    path_token: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="webhook_endpoints")
    user: Mapped["User"] = relationship("User", back_populates="webhook_endpoints")
