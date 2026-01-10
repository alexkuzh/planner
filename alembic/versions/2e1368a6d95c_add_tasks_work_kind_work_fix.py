"""add tasks.work_kind work/fix

Revision ID: 2e1368a6d95c
Revises: 8752d58f38a0
Create Date: 2026-01-08 23:32:03.905531

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2e1368a6d95c'
down_revision: Union[str, Sequence[str], None] = '8752d58f38a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    work_kind = postgresql.ENUM("work", "fix", name="work_kind")
    work_kind.create(op.get_bind(), checkfirst=True)

    op.add_column("tasks", sa.Column("work_kind", work_kind, nullable=False, server_default="work"))
    op.create_index("ix_tasks_deliverable_work_kind", "tasks", ["deliverable_id", "work_kind"])



def downgrade() -> None:
    work_kind = postgresql.ENUM("work", "fix", name="work_kind")
    work_kind.create(op.get_bind(), checkfirst=True)

    op.add_column("tasks", sa.Column("work_kind", work_kind, nullable=False, server_default="work"))
    op.create_index("ix_tasks_deliverable_work_kind", "tasks", ["deliverable_id", "work_kind"])