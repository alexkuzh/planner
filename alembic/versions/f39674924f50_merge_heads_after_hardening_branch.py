"""merge heads after hardening branch

Revision ID: f39674924f50
Revises: 0f1c85caecb1, ad30fbb91da1
Create Date: 2026-01-10 16:31:07.398765

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f39674924f50'
down_revision: Union[str, Sequence[str], None] = ('0f1c85caecb1', 'ad30fbb91da1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
