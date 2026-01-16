"""merge fsm v4 data migration head

Revision ID: f6adea8f8222
Revises: 8d343d3359eb, fsm_v4_data_migration
Create Date: 2026-01-16 11:06:32.752246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6adea8f8222'
down_revision: Union[str, Sequence[str], None] = ('8d343d3359eb', 'fsm_v4_data_migration')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
