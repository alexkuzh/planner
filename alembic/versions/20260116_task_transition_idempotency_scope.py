from alembic import op

# revision identifiers, used by Alembic.
revision = "72de460e4dd5"
down_revision = "8d343d3359eb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) drop old scope (org_id, client_event_id)
    op.execute('DROP INDEX IF EXISTS "uq_task_transitions_org_client_event";')

    # 2) create new scope (task_id, client_event_id)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS "uq_task_transitions_task_client_event"
        ON public.task_transitions (task_id, client_event_id)
        WHERE client_event_id IS NOT NULL;
    """)


def downgrade() -> None:
    # rollback to old behavior
    op.execute('DROP INDEX IF EXISTS "uq_task_transitions_task_client_event";')

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS "uq_task_transitions_org_client_event"
        ON public.task_transitions (org_id, client_event_id)
        WHERE client_event_id IS NOT NULL;
    """)
