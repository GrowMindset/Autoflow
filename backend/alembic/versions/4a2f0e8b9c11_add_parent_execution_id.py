"""add parent execution id to executions

Revision ID: 4a2f0e8b9c11
Revises: 9f3e8b7a1c2d
Create Date: 2026-05-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4a2f0e8b9c11"
down_revision: Union[str, Sequence[str], None] = "9f3e8b7a1c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "executions",
        sa.Column("parent_execution_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_executions_parent_execution_id_executions",
        "executions",
        "executions",
        ["parent_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_executions_parent_execution_id_executions",
        "executions",
        type_="foreignkey",
    )
    op.drop_column("executions", "parent_execution_id")
