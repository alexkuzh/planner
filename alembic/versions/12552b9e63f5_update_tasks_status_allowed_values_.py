"""update tasks.status allowed values (blocked/available/submitted)

Revision ID: 12552b9e63f5
Revises: e6ff5f377d44
Create Date: 2026-01-15 23:13:22.387238

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12552b9e63f5'
down_revision: Union[str, Sequence[str], None] = 'e6ff5f377d44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
