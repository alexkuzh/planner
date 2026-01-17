"""M7.1 temporal invariants for task_transitions row_version

Revision ID: 1b7a2c4d5e6f
Revises: 9c1d2e3f4a5b
Create Date: 2026-01-16
"""

from alembic import op

revision = "1b7a2c4d5e6f"
down_revision = "9c1d2e3f4a5b"
branch_labels = None
depends_on = None


def upgrade():
    # --- safety checks (fail fast if existing bad data) ---
    op.execute(
        """
        DO $$
        BEGIN
            -- 1) no NULL result_row_version
            IF EXISTS (
                SELECT 1
                FROM task_transitions
                WHERE result_row_version IS NULL
            ) THEN
                RAISE EXCEPTION 'M7.1 violation: task_transitions.result_row_version contains NULLs';
            END IF;

            -- 2) expected -> result must be +1 when expected is present
            IF EXISTS (
                SELECT 1
                FROM task_transitions
                WHERE expected_row_version IS NOT NULL
                  AND result_row_version <> expected_row_version + 1
            ) THEN
                RAISE EXCEPTION 'M7.1 violation: task_transitions.result_row_version != expected_row_version + 1';
            END IF;

            -- 3) uniqueness of (org_id, task_id, result_row_version)
            IF EXISTS (
                SELECT org_id, task_id, result_row_version
                FROM task_transitions
                GROUP BY org_id, task_id, result_row_version
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'M7.1 violation: duplicate (org_id, task_id, result_row_version) in task_transitions';
            END IF;
        END$$;
        """
    )

    # --- enforce NOT NULL ---
    op.execute(
        "ALTER TABLE task_transitions ALTER COLUMN result_row_version SET NOT NULL"
    )

    # --- add CHECK: expected -> result = expected + 1 ---
    op.create_check_constraint(
        "ck_task_transitions_expected_plus_one",
        "task_transitions",
        "expected_row_version IS NULL OR result_row_version = expected_row_version + 1",
    )

    # --- add UNIQUE index on version per task ---
    op.create_index(
        "uq_task_transitions_task_result_rv",
        "task_transitions",
        ["org_id", "task_id", "result_row_version"],
        unique=True,
    )


def downgrade():
    # Safe drops
    op.execute("DROP INDEX IF EXISTS uq_task_transitions_task_result_rv")
    op.execute(
        "ALTER TABLE task_transitions DROP CONSTRAINT IF EXISTS ck_task_transitions_expected_plus_one"
    )

    # Relax NOT NULL
    op.execute(
        "ALTER TABLE task_transitions ALTER COLUMN result_row_version DROP NOT NULL"
    )
