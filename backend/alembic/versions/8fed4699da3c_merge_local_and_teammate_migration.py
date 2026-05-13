"""merge_local_and_teammate_migration

Revision ID: 8fed4699da3c
Revises: 5e8c4a1f9b7d, e8b4f23a9d17
Create Date: 2026-05-13 16:28:47.522197

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8fed4699da3c'
down_revision: Union[str, Sequence[str], None] = ('5e8c4a1f9b7d', 'e8b4f23a9d17')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
