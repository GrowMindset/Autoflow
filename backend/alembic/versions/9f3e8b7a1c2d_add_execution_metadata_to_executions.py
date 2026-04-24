"""add execution_metadata to executions

Revision ID: 9f3e8b7a1c2d
Revises: 7b2d9f31d8aa
Create Date: 2026-04-23 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9f3e8b7a1c2d"
down_revision: Union[str, Sequence[str], None] = "7b2d9f31d8aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "executions",
        sa.Column("execution_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("executions", "execution_metadata")

