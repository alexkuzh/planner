"""DB-hardening M6: project-consistent FKs

Revision ID: 9c1d2e3f4a5b
Revises: 8f3c2a1e9d40
Create Date: 2026-01-16
"""

from alembic import op

revision = "9c1d2e3f4a5b"
down_revision = "8f3c2a1e9d40"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Supporting UNIQUE constraints so we can reference (org_id, project_id, id)
    op.execute(
        """
        ALTER TABLE deliverables
        ADD CONSTRAINT uq_deliverables_org_project_id
        UNIQUE (org_id, project_id, id)
        """
    )
    op.execute(
        """
        ALTER TABLE qc_inspections
        ADD CONSTRAINT uq_qc_inspections_org_project_id
        UNIQUE (org_id, project_id, id)
        """
    )

    # 2) Safety checks: refuse migration if bad data already exists
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM tasks t
                JOIN deliverables d ON d.org_id = t.org_id AND d.id = t.deliverable_id
                WHERE t.deliverable_id IS NOT NULL
                  AND t.project_id <> d.project_id
            ) THEN
                RAISE EXCEPTION 'M6 violation: tasks.deliverable_id cross-project reference detected';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM qc_inspections q
                JOIN deliverables d ON d.org_id = q.org_id AND d.id = q.deliverable_id
                WHERE q.project_id <> d.project_id
            ) THEN
                RAISE EXCEPTION 'M6 violation: qc_inspections.deliverable_id cross-project reference detected';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM deliverable_signoffs s
                JOIN deliverables d ON d.org_id = s.org_id AND d.id = s.deliverable_id
                WHERE s.project_id <> d.project_id
            ) THEN
                RAISE EXCEPTION 'M6 violation: deliverable_signoffs.deliverable_id cross-project reference detected';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM tasks t
                JOIN qc_inspections q ON q.org_id = t.org_id AND q.id = t.qc_inspection_id
                WHERE t.qc_inspection_id IS NOT NULL
                  AND t.project_id <> q.project_id
            ) THEN
                RAISE EXCEPTION 'M6 violation: tasks.qc_inspection_id cross-project reference detected';
            END IF;
        END$$;
        """
    )

    # 3) Drop legacy org-only FKs
    op.drop_constraint("fk_tasks_deliverable_org", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_qc_inspection_org", "tasks", type_="foreignkey")
    op.drop_constraint("fk_qc_deliverable_org", "qc_inspections", type_="foreignkey")
    op.drop_constraint("fk_signoffs_deliverable_org", "deliverable_signoffs", type_="foreignkey")

    # 4) Add project-consistent composite FKs
    # NOTE: For tasks we cannot use ON DELETE SET NULL because project_id/org_id are NOT NULL.
    op.execute(
        """
        ALTER TABLE tasks
        ADD CONSTRAINT fk_tasks_deliverable_project
        FOREIGN KEY (org_id, project_id, deliverable_id)
        REFERENCES deliverables (org_id, project_id, id)
        ON DELETE RESTRICT
        """
    )

    op.execute(
        """
        ALTER TABLE tasks
        ADD CONSTRAINT fk_tasks_qc_inspection_project
        FOREIGN KEY (org_id, project_id, qc_inspection_id)
        REFERENCES qc_inspections (org_id, project_id, id)
        ON DELETE RESTRICT
        """
    )

    op.execute(
        """
        ALTER TABLE qc_inspections
        ADD CONSTRAINT fk_qc_inspections_deliverable_project
        FOREIGN KEY (org_id, project_id, deliverable_id)
        REFERENCES deliverables (org_id, project_id, id)
        ON DELETE CASCADE
        """
    )

    op.execute(
        """
        ALTER TABLE deliverable_signoffs
        ADD CONSTRAINT fk_signoffs_deliverable_project
        FOREIGN KEY (org_id, project_id, deliverable_id)
        REFERENCES deliverables (org_id, project_id, id)
        ON DELETE CASCADE
        """
    )


def downgrade():
    # --- drop composite FKs (safe) ---
    op.execute(
        "ALTER TABLE deliverable_signoffs "
        "DROP CONSTRAINT IF EXISTS fk_signoffs_deliverable_project"
    )
    op.execute(
        "ALTER TABLE qc_inspections "
        "DROP CONSTRAINT IF EXISTS fk_qc_inspections_deliverable_project"
    )
    op.execute(
        "ALTER TABLE tasks "
        "DROP CONSTRAINT IF EXISTS fk_tasks_qc_inspection_project"
    )
    op.execute(
        "ALTER TABLE tasks "
        "DROP CONSTRAINT IF EXISTS fk_tasks_deliverable_project"
    )

    # --- restore legacy org-only FKs (ONLY IF NOT EXISTS) ---
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_tasks_deliverable_org'
            ) THEN
                ALTER TABLE tasks
                ADD CONSTRAINT fk_tasks_deliverable_org
                FOREIGN KEY (org_id, deliverable_id)
                REFERENCES deliverables (org_id, id)
                ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_tasks_qc_inspection_org'
            ) THEN
                ALTER TABLE tasks
                ADD CONSTRAINT fk_tasks_qc_inspection_org
                FOREIGN KEY (org_id, qc_inspection_id)
                REFERENCES qc_inspections (org_id, id)
                ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_qc_deliverable_org'
            ) THEN
                ALTER TABLE qc_inspections
                ADD CONSTRAINT fk_qc_deliverable_org
                FOREIGN KEY (org_id, deliverable_id)
                REFERENCES deliverables (org_id, id)
                ON DELETE CASCADE;
            END IF;
        END$$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_signoffs_deliverable_org'
            ) THEN
                ALTER TABLE deliverable_signoffs
                ADD CONSTRAINT fk_signoffs_deliverable_org
                FOREIGN KEY (org_id, deliverable_id)
                REFERENCES deliverables (org_id, id)
                ON DELETE CASCADE;
            END IF;
        END$$;
        """
    )

    # --- drop supporting UNIQUEs (safe) ---
    op.execute(
        "ALTER TABLE qc_inspections "
        "DROP CONSTRAINT IF EXISTS uq_qc_inspections_org_project_id"
    )
    op.execute(
        "ALTER TABLE deliverables "
        "DROP CONSTRAINT IF EXISTS uq_deliverables_org_project_id"
    )
