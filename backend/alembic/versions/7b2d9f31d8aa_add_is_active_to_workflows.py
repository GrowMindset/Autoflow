"""add is_active to workflows

Revision ID: 7b2d9f31d8aa
Revises: d6e34a62534c
Create Date: 2026-04-21 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b2d9f31d8aa"
down_revision: Union[str, Sequence[str], None] = "d6e34a62534c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("workflows", "is_active")

