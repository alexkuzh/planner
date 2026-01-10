"""add task milestone flag

Revision ID: eaff91734be9
Revises: ccc7cd883a4b
Create Date: 2026-01-05 22:13:14.705838

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eaff91734be9'
down_revision: Union[str, Sequence[str], None] = 'ccc7cd883a4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("is_milestone", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # optional: уберём server_default, чтобы default жил в приложении
    op.alter_column("tasks", "is_milestone", server_default=None)


def downgrade() -> None:
    op.drop_column("tasks", "is_milestone")