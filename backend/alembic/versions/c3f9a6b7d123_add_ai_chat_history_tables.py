"""add ai chat history tables

Revision ID: c3f9a6b7d123
Revises: 9f3e8b7a1c2d
Create Date: 2026-04-27 20:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c3f9a6b7d123"
down_revision: Union[str, Sequence[str], None] = "9f3e8b7a1c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_chat_messages",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("scope_key", sa.String(length=120), nullable=False),
        sa.Column(
            "message_index",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_chat_messages_user_scope_index",
        "ai_chat_messages",
        ["user_id", "scope_key", "message_index"],
        unique=False,
    )

    op.create_table(
        "ai_chat_states",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("scope_key", sa.String(length=120), nullable=False),
        sa.Column(
            "state_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "scope_key", name="uq_ai_chat_states_user_scope"),
    )


def downgrade() -> None:
    op.drop_table("ai_chat_states")
    op.drop_index("ix_ai_chat_messages_user_scope_index", table_name="ai_chat_messages")
    op.drop_table("ai_chat_messages")
