"""db hardening: M5b force org-safe FK for task_allocations

Revision ID: 8f3c2a1e9d40
Revises: 6d1a2b0c4f77
Create Date: 2026-01-16
"""
from typing import Sequence, Union
from alembic import op

revision: str = "8f3c2a1e9d40"
down_revision: Union[str, Sequence[str], None] = "6d1a2b0c4f77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Normalize existing data so FK can be applied safely:
    # if any allocation has wrong org_id, align it to the task's org_id.
    op.execute(
        """
        UPDATE task_allocations ta
        SET org_id = t.org_id
        FROM tasks t
        WHERE ta.task_id = t.id
          AND ta.org_id IS DISTINCT FROM t.org_id;
        """
    )

    # 2) Drop ANY FK from task_allocations to tasks (names vary; we drop by referenced table)
    op.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN
                SELECT conname
                FROM pg_constraint
                WHERE contype = 'f'
                  AND conrelid = 'task_allocations'::regclass
                  AND confrelid = 'tasks'::regclass
            LOOP
                EXECUTE format('ALTER TABLE task_allocations DROP CONSTRAINT %I', r.conname);
            END LOOP;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_task_allocations_task_org'
            ) THEN
                ALTER TABLE task_allocations
                ADD CONSTRAINT fk_task_allocations_task_org
                FOREIGN KEY (org_id, task_id)
                REFERENCES tasks (org_id, id)
                ON DELETE CASCADE;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Drop composite FK
    op.execute("ALTER TABLE task_allocations DROP CONSTRAINT IF EXISTS fk_task_allocations_task_org")

    # Restore legacy FK (task_id -> tasks.id) with a stable name
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_task_allocations_task_id'
            ) THEN
                ALTER TABLE task_allocations
                ADD CONSTRAINT fk_task_allocations_task_id
                FOREIGN KEY (task_id)
                REFERENCES tasks (id)
                ON DELETE CASCADE;
            END IF;
        END
        $$;
        """
    )
