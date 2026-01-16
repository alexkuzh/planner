"""restore_missing_revision

Revision ID: 3bd64fe36863
Revises: 56dce7ebb756
Create Date: 2026-01-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3bd64fe36863"
down_revision: Union[str, Sequence[str], None] = "56dce7ebb756"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # восстановительная заглушка для починки графа ревизий
    pass


def downgrade() -> None:
    pass
