"""db hardening: M4 fix-task consistency checks

Revision ID: 3f6a1d4c2e90
Revises: 9c8e7f0a1b33
Create Date: 2026-01-16
"""
from typing import Sequence, Union
from alembic import op


revision: str = "3f6a1d4c2e90"
down_revision: Union[str, Sequence[str], None] = "9c8e7f0a1b33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_tasks_fix_fields_consistent'
            ) THEN
                ALTER TABLE tasks
                ADD CONSTRAINT ck_tasks_fix_fields_consistent
                CHECK (
                    (
                        work_kind = 'work'
                        AND origin_task_id IS NULL
                        AND fix_source IS NULL
                        AND fix_severity IS NULL
                        AND qc_inspection_id IS NULL
                    )
                    OR
                    (
                        work_kind = 'fix'
                        AND origin_task_id IS NOT NULL
                        AND fix_source IS NOT NULL
                        AND fix_severity IS NOT NULL
                        AND (
                            (fix_source = 'qc_reject' AND qc_inspection_id IS NOT NULL)
                            OR
                            (fix_source <> 'qc_reject' AND qc_inspection_id IS NULL)
                        )
                    )
                );
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_fix_fields_consistent")
