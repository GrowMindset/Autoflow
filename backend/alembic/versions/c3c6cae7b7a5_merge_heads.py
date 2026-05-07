"""merge heads

Revision ID: c3c6cae7b7a5
Revises: 4a2f0e8b9c11, c3f9a6b7d123
Create Date: 2026-05-07 11:46:18.266030

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3c6cae7b7a5'
down_revision: Union[str, Sequence[str], None] = ('4a2f0e8b9c11', 'c3f9a6b7d123')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
