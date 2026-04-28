"""Persistent AI assistant chat history models.

Stores AI chat messages and per-scope conversation state so chat context
survives browser refreshes and future sessions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

from app.models.base import Base, CreatedAtMixin, JSONB, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class AIChatMessage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ai_chat_messages"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_key: Mapped[str] = mapped_column(String(120), nullable=False)
    message_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="ai_chat_messages")

    __table_args__ = (
        Index(
            "ix_ai_chat_messages_user_scope_index",
            "user_id",
            "scope_key",
            "message_index",
        ),
    )


class AIChatState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_chat_states"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_key: Mapped[str] = mapped_column(String(120), nullable=False)
    state_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    user: Mapped["User"] = relationship("User", back_populates="ai_chat_states")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "scope_key",
            name="uq_ai_chat_states_user_scope",
        ),
    )
