"""add workflow versions table

Revision ID: 5e8c4a1f9b7d
Revises: c3c6cae7b7a5
Create Date: 2026-05-13 17:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "5e8c4a1f9b7d"
down_revision: Union[str, Sequence[str], None] = "c3c6cae7b7a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_versions",
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_id",
            "version_number",
            name="uq_workflow_versions_workflow_id_version_number",
        ),
    )
    op.create_index(
        "ix_workflow_versions_workflow_id_created_at",
        "workflow_versions",
        ["workflow_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_versions_workflow_id_created_at", table_name="workflow_versions")
    op.drop_table("workflow_versions")
