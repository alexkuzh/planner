"""add row_version columns to task_transitions

Revision ID: e6ff5f377d44
Revises: f39674924f50
Create Date: 2026-01-10 22:06:52.770792

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'e6ff5f377d44'
down_revision: Union[str, Sequence[str], None] = 'f39674924f50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    exists = conn.execute(
        text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'task_transitions'
          AND column_name = 'expected_row_version'
        """)
    ).first()

    if not exists:
        op.add_column(
            "task_transitions",
            sa.Column("expected_row_version", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    pass