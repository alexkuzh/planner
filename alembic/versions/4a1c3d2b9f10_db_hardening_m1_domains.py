"""db hardening: M1 domains (status/result/priority)

Revision ID: 4a1c3d2b9f10
Revises: f6995bb146e4
Create Date: 2026-01-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a1c3d2b9f10"
down_revision: Union[str, Sequence[str], None] = "f6995bb146e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # tasks.status allowed values
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_tasks_status_allowed'
            ) THEN
                ALTER TABLE tasks
                ADD CONSTRAINT ck_tasks_status_allowed
                CHECK (status IN (
                    'blocked',
                    'available',
                    'assigned',
                    'in_progress',
                    'submitted',
                    'done',
                    'canceled'
                ));
            END IF;
        END
        $$;
        """
    )

    # tasks.priority >= 0
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_tasks_priority_nonneg'
            ) THEN
                ALTER TABLE tasks
                ADD CONSTRAINT ck_tasks_priority_nonneg
                CHECK (priority >= 0);
            END IF;
        END
        $$;
        """
    )

    # qc_inspections.result allowed values
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_qc_inspections_result_allowed'
            ) THEN
                ALTER TABLE qc_inspections
                ADD CONSTRAINT ck_qc_inspections_result_allowed
                CHECK (result IN ('approved', 'rejected'));
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE qc_inspections DROP CONSTRAINT IF EXISTS ck_qc_inspections_result_allowed")
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_priority_nonneg")
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_status_allowed")
