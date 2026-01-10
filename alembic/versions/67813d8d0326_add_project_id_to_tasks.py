"""add project_id to tasks

Revision ID: 67813d8d0326
Revises: 56dce7ebb756
Create Date: 2026-01-09 21:53:18.568237

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '67813d8d0326'
down_revision: Union[str, Sequence[str], None] = '56dce7ebb756'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    # 1) добавляем колонку (для существующих строк даём временный default)
    op.add_column(
        "tasks",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )

    # 2) убираем default, чтобы приложение всегда присылало project_id само
    op.alter_column("tasks", "project_id", server_default=None)


def downgrade() -> None:
    op.drop_column("tasks", "project_id")