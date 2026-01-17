"""M8.1.A temporal invariants: tasks assigned_at >= created_at

Revision ID: 6a4d9c2e8b10
Revises: 3c9e7d8f1a2b
Create Date: 2026-01-16
"""

from alembic import op

revision = "6a4d9c2e8b10"
down_revision = "3c9e7d8f1a2b"
branch_labels = None
depends_on = None


def upgrade():
    # --- safety checks ---
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM tasks
                WHERE assigned_at IS NOT NULL
                  AND assigned_at < created_at
            ) THEN
                RAISE EXCEPTION 'M8.1.A violation: assigned_at < created_at';
            END IF;
        END$$;
        """
    )

    op.create_check_constraint(
        "ck_tasks_created_le_assigned",
        "tasks",
        "assigned_at IS NULL OR created_at <= assigned_at",
    )


def downgrade():
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS ck_tasks_created_le_assigned")
