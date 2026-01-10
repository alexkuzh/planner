"""db_hardening_indexes_concurrently

Revision ID: ad30fbb91da1
Revises: 02869b48608a
Create Date: 2026-01-10 15:10:15.729628

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad30fbb91da1'
down_revision: Union[str, Sequence[str], None] = '02869b48608a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
