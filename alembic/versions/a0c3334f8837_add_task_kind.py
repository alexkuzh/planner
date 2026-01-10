"""add task kind

Revision ID: a0c3334f8837
Revises: bce835fa1cce
Create Date: 2026-01-05 20:23:56.930730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0c3334f8837'
down_revision: Union[str, Sequence[str], None] = 'bce835fa1cce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("kind", sa.String(), nullable=False, server_default="production"),
    )
    op.add_column(
        "tasks",
        sa.Column("other_kind_label", sa.Text(), nullable=True),
    )

    # После добавления ставим default только на уровне приложения (в модели),
    # в БД server_default можно убрать, если хочешь чистоты:
    op.alter_column("tasks", "kind", server_default=None)


def downgrade() -> None:
    op.drop_column("tasks", "other_kind_label")
    op.drop_column("tasks", "kind")