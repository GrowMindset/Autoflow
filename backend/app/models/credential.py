"""Third-party credential model reserved for later phases.

This file defines the `app_credentials` table. The schema guide says the table
must exist now even though application logic should not use it until Phase 3.
Each row stores one connected app credential for one user, with flexible JSONB
token storage because different integrations need different token shapes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, JSONB, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class AppCredential(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Stored third-party app credential for a user, reserved for Phase 3."""

    __tablename__ = "app_credentials"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_name: Mapped[str] = mapped_column(String(50), nullable=False)
    token_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="app_credentials")
