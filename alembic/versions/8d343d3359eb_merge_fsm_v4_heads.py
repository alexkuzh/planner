"""merge fsm v4 heads

Revision ID: 8d343d3359eb
Revises: 12552b9e63f5, update_fsm_v4
Create Date: 2026-01-16 09:51:25.368656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d343d3359eb'
down_revision: Union[str, Sequence[str], None] = ('12552b9e63f5', 'update_fsm_v4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
