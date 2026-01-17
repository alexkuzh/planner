"""M7.2.A lifecycle uniqueness: one fix-task per QC reject

Revision ID: 3c9e7d8f1a2b
Revises: 1b7a2c4d5e6f
Create Date: 2026-01-16
"""

from alembic import op
import sqlalchemy as sa

revision = "3c9e7d8f1a2b"
down_revision = "1b7a2c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    # Safety-check: no duplicates already exist
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT org_id, origin_task_id
                FROM tasks
                WHERE work_kind = 'fix'::work_kind
                  AND fix_source = 'qc_reject'::fix_source
                GROUP BY org_id, origin_task_id
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'M7.2.A violation: multiple fix tasks for same origin_task_id with fix_source=qc_reject';
            END IF;
        END$$;
        """
    )

    # Partial UNIQUE index: one qc_reject fix-task per origin task (per org)
    op.create_index(
        "uq_tasks_one_fix_per_qc_reject",
        "tasks",
        ["org_id", "origin_task_id"],
        unique=True,
        postgresql_where=sa.text(
            "work_kind = 'fix'::work_kind AND fix_source = 'qc_reject'::fix_source"
        ),
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_tasks_one_fix_per_qc_reject")
