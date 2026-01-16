"""db hardening: M2 status <-> assignment consistency

Revision ID: 7b2f8c1d0a21
Revises: 4a1c3d2b9f10
Create Date: 2026-01-16
"""
from typing import Sequence, Union
from alembic import op


revision: str = "7b2f8c1d0a21"
down_revision: Union[str, Sequence[str], None] = "4a1c3d2b9f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Normalize existing data that is impossible via FSM
    # blocked / available must not have assignee
    op.execute(
        """
        UPDATE tasks
        SET assigned_to = NULL,
            assigned_at = NULL
        WHERE status IN ('blocked', 'available')
          AND (assigned_to IS NOT NULL OR assigned_at IS NOT NULL);
        """
    )

    # 2. Add CHECK constraint (idempotent)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_tasks_assignment_matches_status'
            ) THEN
                ALTER TABLE tasks
                ADD CONSTRAINT ck_tasks_assignment_matches_status
                CHECK (
                    (
                        status IN ('blocked', 'available')
                        AND assigned_to IS NULL
                        AND assigned_at IS NULL
                    )
                    OR
                    (
                        status IN ('assigned', 'in_progress', 'submitted')
                        AND assigned_to IS NOT NULL
                        AND assigned_at IS NOT NULL
                    )
                    OR
                    (
                        status IN ('done', 'canceled')
                    )
                );
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_assignment_matches_status"
    )
