"""Drop obsolete ck_tasks_assigned_le_updated (M8 fix)

Revision ID: 6a4d9c2e8b11
Revises: 6a4d9c2e8b10
Create Date: 2026-01-17
"""

from alembic import op

revision = "6a4d9c2e8b11"
down_revision = "6a4d9c2e8b10"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_assigned_le_updated"
    )


def downgrade():
    # сознательно НЕ восстанавливаем — constraint признан ошибочным
    pass
