"""add workflow published_at

Revision ID: e8b4f23a9d17
Revises: c3c6cae7b7a5
Create Date: 2026-05-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8b4f23a9d17"
down_revision: Union[str, Sequence[str], None] = "c3c6cae7b7a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE workflows SET published_at = now() "
        "WHERE is_published IS TRUE AND published_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("workflows", "published_at")
