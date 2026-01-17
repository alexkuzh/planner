"""M9.1.A lifecycle uniqueness: one qc_inspection per deliverable

Revision ID: 9f2a1c7d0b3e
Revises: 6a4d9c2e8b11
Create Date: 2026-01-17
"""

from alembic import op

revision = "9f2a1c7d0b3e"
down_revision = "6a4d9c2e8b11"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT org_id, project_id, deliverable_id
                FROM qc_inspections
                GROUP BY org_id, project_id, deliverable_id
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'M9.1.A violation: multiple qc_inspections for same (org, project, deliverable)';
            END IF;
        END$$;
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_qc_one_per_deliverable
        ON qc_inspections (org_id, project_id, deliverable_id)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_qc_one_per_deliverable")
