"""db hardening: M3 WIP=1 unique partial index

Revision ID: 9c8e7f0a1b33
Revises: 7b2f8c1d0a21
Create Date: 2026-01-16
"""
from typing import Sequence, Union

from alembic import op


revision: str = "9c8e7f0a1b33"
down_revision: Union[str, Sequence[str], None] = "7b2f8c1d0a21"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_tasks_wip1_org_assignee_active"


def upgrade() -> None:
    # Enforce WIP=1 at DB level:
    # at most one active task per (org_id, assigned_to)
    # active statuses: assigned, in_progress, submitted
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'i'
                  AND c.relname = '{INDEX_NAME}'
            ) THEN
                CREATE UNIQUE INDEX {INDEX_NAME}
                ON tasks (org_id, assigned_to)
                WHERE assigned_to IS NOT NULL
                  AND status IN ('assigned', 'in_progress', 'submitted');
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
