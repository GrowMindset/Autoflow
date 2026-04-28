"""User account model.

This file defines the `users` table described in the schema guide. A user owns
workflows, executions, webhook endpoints, and future app credentials. The model
stores only authentication essentials: email, username, hashed password, and
creation timestamp.

The relationship fields make it easy to navigate from a user object to the
records they own, while the actual database separation rule is still enforced
in queries by filtering on `user_id`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ai_chat_history import AIChatMessage, AIChatState
    from app.models.credential import AppCredential
    from app.models.executions import Execution
    from app.models.webhook import WebhookEndpoint
    from app.models.workflows import Workflow


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Registered user account used for authentication and ownership."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)

    workflows: Mapped[list["Workflow"]] = relationship(
        "Workflow", back_populates="user", cascade="all, delete-orphan"
    )
    executions: Mapped[list["Execution"]] = relationship(
        "Execution", back_populates="user", cascade="all, delete-orphan"
    )
    app_credentials: Mapped[list["AppCredential"]] = relationship(
        "AppCredential", back_populates="user", cascade="all, delete-orphan"
    )
    webhook_endpoints: Mapped[list["WebhookEndpoint"]] = relationship(
        "WebhookEndpoint", back_populates="user", cascade="all, delete-orphan"
    )
    ai_chat_messages: Mapped[list["AIChatMessage"]] = relationship(
        "AIChatMessage", back_populates="user", cascade="all, delete-orphan"
    )
    ai_chat_states: Mapped[list["AIChatState"]] = relationship(
        "AIChatState", back_populates="user", cascade="all, delete-orphan"
    )
