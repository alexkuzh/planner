"""db hardening: M5 org-safe foreign keys

Revision ID: 6d1a2b0c4f77
Revises: 3f6a1d4c2e90
Create Date: 2026-01-16
"""
from typing import Sequence, Union
from alembic import op


revision: str = "6d1a2b0c4f77"
down_revision: Union[str, Sequence[str], None] = "3f6a1d4c2e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) tasks(deliverable_id) must match org: (org_id, deliverable_id) -> deliverables(org_id, id)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_tasks_deliverable_org'
            ) THEN
                ALTER TABLE tasks
                ADD CONSTRAINT fk_tasks_deliverable_org
                FOREIGN KEY (org_id, deliverable_id)
                REFERENCES deliverables (org_id, id)
                ON DELETE SET NULL;
            END IF;
        END
        $$;
        """
    )

    # 2) task_allocations must match task org: (org_id, task_id) -> tasks(org_id, id)
    # drop old FK if exists (name may vary, so we drop by scanning)
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
            LOOP
                -- Drop any FK that references tasks(id) only (legacy)
                IF pg_get_constraintdef((SELECT oid FROM pg_constraint WHERE conname=r.conname)) LIKE '%FOREIGN KEY (task_id)%REFERENCES tasks(id)%' THEN
                    EXECUTE format('ALTER TABLE task_allocations DROP CONSTRAINT %I', r.conname);
                END IF;
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
    op.execute("ALTER TABLE task_allocations DROP CONSTRAINT IF EXISTS fk_task_allocations_task_org")
    # legacy FK обратно не восстанавливаем по имени (он мог быть разный).
    # Если тебе нужно строго вернуть старый FK на task_id, скажи — добавлю явное имя из твоей схемы.
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS fk_tasks_deliverable_org")
