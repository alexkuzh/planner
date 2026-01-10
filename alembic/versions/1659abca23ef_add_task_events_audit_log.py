"""add task events audit log

Revision ID: 1659abca23ef
Revises: 455e315835e2
Create Date: 2026-01-04 19:53:34.771576
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "1659abca23ef"
down_revision: Union[str, Sequence[str], None] = "455e315835e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    return bool(
        conn.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"),
            {"t": f"public.{name}"},
        ).scalar()
    )

def _tasks_id_is_uuid() -> bool:
    conn = op.get_bind()
    # udt_name будет 'uuid' если колонка UUID, иначе 'int4', 'int8', и т.п.
    udt = conn.execute(
        text("""
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='tasks'
              AND column_name='id'
            LIMIT 1
        """)
    ).scalar()
    return (udt == "uuid")

def _col_udt(table: str, col: str) -> str | None:
    conn = op.get_bind()
    return conn.execute(
        text("""
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name=:t
              AND column_name=:c
            LIMIT 1
        """),
        {"t": table, "c": col},
    ).scalar()


def upgrade() -> None:
    """Upgrade schema."""

    # 1) Remove legacy tables safely (may not exist on fresh DB)
    op.drop_index(op.f("idx_artifacts_object"), table_name="artifacts", if_exists=True)
    op.drop_index(op.f("idx_artifacts_task_time"), table_name="artifacts", if_exists=True)
    op.drop_table("artifacts", if_exists=True)

    op.drop_index(op.f("idx_dep_predecessor"), table_name="task_dependencies", if_exists=True)
    op.drop_index(op.f("idx_dep_successor"), table_name="task_dependencies", if_exists=True)
    op.drop_table("task_dependencies", if_exists=True)

    # 2) task_transitions refactor (only if table exists)
    if _table_exists("task_transitions"):
        # Bring enums/text columns back to String (this migration later flips them back on downgrade)
        op.alter_column(
            "task_transitions",
            "action",
            existing_type=sa.TEXT(),
            type_=sa.String(),
            existing_nullable=False,
        )
        op.alter_column(
            "task_transitions",
            "from_status",
            existing_type=sa.TEXT(),
            type_=sa.String(),
            existing_nullable=False,
        )
        op.alter_column(
            "task_transitions",
            "to_status",
            existing_type=sa.TEXT(),
            type_=sa.String(),
            existing_nullable=False,
        )
        op.alter_column(
            "task_transitions",
            "payload",
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            type_=sa.JSON(),
            existing_nullable=False,
            existing_server_default=sa.text("'{}'::jsonb"),
        )

        # Drop legacy indexes/constraints safely
        op.drop_index(
            op.f("idx_task_transitions_task_time"),
            table_name="task_transitions",
            if_exists=True,
        )
        op.drop_index(
            op.f("uq_task_transitions_idempotency"),
            table_name="task_transitions",
            if_exists=True,
        )
        op.execute("ALTER TABLE task_transitions DROP CONSTRAINT IF EXISTS task_transitions_task_id_fkey")


    # 3) tasks indexes/constraints refactor (only if tasks exists)
    if _table_exists("tasks"):
        op.alter_column(
            "tasks",
            "status",
            existing_type=sa.TEXT(),
            type_=sa.String(),
            existing_nullable=False,
        )
        op.drop_index(op.f("idx_tasks_org_parent"), table_name="tasks", if_exists=True)
        op.drop_index(op.f("idx_tasks_org_project_assigned"), table_name="tasks", if_exists=True)
        op.drop_index(op.f("idx_tasks_org_project_priority"), table_name="tasks", if_exists=True)
        op.drop_index(op.f("idx_tasks_org_project_status"), table_name="tasks", if_exists=True)
        # на разных исторических схемах имя могло отличаться или FK мог отсутствовать
        op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS fk_tasks_parent")

    # 4) task_events: change task_id int -> uuid and add FK (ONLY if tables exist)
    # IMPORTANT:
    # - We do NOT create FK earlier because task_events.task_id was int and tasks.id is uuid.
    # - On fresh DB task_events might not exist yet depending on migration history.
    if _table_exists("task_events") and _table_exists("tasks") and _tasks_id_is_uuid():
        # If there are existing rows, conversion int->uuid is impossible. This is MVP/dev-safe behavior.
        op.execute("DELETE FROM task_events")

        op.alter_column(
            "task_events",
            "task_id",
            existing_type=sa.Integer(),
            type_=postgresql.UUID(as_uuid=True),
            postgresql_using="NULL::uuid",
            nullable=True,  # can tighten later
        )

        # Named FK for stable downgrade
        op.create_foreign_key(
            "task_events_task_id_fkey",
            "task_events",
            "tasks",
            ["task_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) task_events back: drop FK and convert uuid -> int (only if table exists)
    if _table_exists("task_events"):
        # drop FK if exists
        op.drop_constraint(
            "task_events_task_id_fkey",
            "task_events",
            type_="foreignkey",
            if_exists=True,
        )
        if _col_udt("task_events", "task_id") == "uuid":
            # convert back (data already lost; dev/mvp behavior)
            op.alter_column(
                "task_events",
                "task_id",
                existing_type=postgresql.UUID(as_uuid=True),
                type_=sa.Integer(),
                postgresql_using="NULL::integer",
                nullable=True,
            )

    # 2) restore tasks objects (only if tasks exists)
    if _table_exists("tasks"):
        op.create_foreign_key(
            op.f("fk_tasks_parent"),
            "tasks",
            "tasks",
            ["parent_task_id"],
            ["id"],
        )
        op.create_index(
            op.f("idx_tasks_org_project_status"),
            "tasks",
            ["org_id", "project_id", "status"],
            unique=False,
        )
        op.create_index(
            op.f("idx_tasks_org_project_priority"),
            "tasks",
            ["org_id", "project_id", sa.literal_column("priority DESC"), "created_at"],
            unique=False,
        )
        op.create_index(
            op.f("idx_tasks_org_project_assigned"),
            "tasks",
            ["org_id", "project_id", "assigned_to"],
            unique=False,
        )
        op.create_index(
            op.f("idx_tasks_org_parent"),
            "tasks",
            ["org_id", "parent_task_id"],
            unique=False,
        )
        op.alter_column(
            "tasks",
            "status",
            existing_type=sa.String(),
            type_=sa.TEXT(),
            existing_nullable=False,
        )

    # 3) restore task_transitions objects (only if table exists)
    if _table_exists("task_transitions"):
        op.create_foreign_key(
            op.f("task_transitions_task_id_fkey"),
            "task_transitions",
            "tasks",
            ["task_id"],
            ["id"],
        )
        op.create_index(
            op.f("uq_task_transitions_idempotency"),
            "task_transitions",
            ["org_id", "client_event_id"],
            unique=True,
            postgresql_where="(client_event_id IS NOT NULL)",
        )
        op.create_index(
            op.f("idx_task_transitions_task_time"),
            "task_transitions",
            ["org_id", "task_id", sa.literal_column("created_at DESC")],
            unique=False,
        )
        op.alter_column(
            "task_transitions",
            "payload",
            existing_type=sa.JSON(),
            type_=postgresql.JSONB(astext_type=sa.Text()),
            existing_nullable=False,
            existing_server_default=sa.text("'{}'::jsonb"),
        )
        op.alter_column(
            "task_transitions",
            "to_status",
            existing_type=sa.String(),
            type_=sa.TEXT(),
            existing_nullable=False,
        )
        op.alter_column(
            "task_transitions",
            "from_status",
            existing_type=sa.String(),
            type_=sa.TEXT(),
            existing_nullable=False,
        )
        op.alter_column(
            "task_transitions",
            "action",
            existing_type=sa.String(),
            type_=sa.TEXT(),
            existing_nullable=False,
        )

    # 4) recreate dropped legacy tables (dev only). Do it only if tasks exists (FKs reference tasks)
    if _table_exists("tasks"):
        op.create_table(
            "task_dependencies",
            sa.Column("org_id", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column("project_id", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column("predecessor_id", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column("successor_id", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column("created_by", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column(
                "created_at",
                postgresql.TIMESTAMP(timezone=True),
                server_default=sa.text("now()"),
                autoincrement=False,
                nullable=False,
            ),
            sa.CheckConstraint("predecessor_id <> successor_id", name=op.f("dep_not_self")),
            sa.ForeignKeyConstraint(
                ["predecessor_id"],
                ["tasks.id"],
                name=op.f("task_dependencies_predecessor_id_fkey"),
            ),
            sa.ForeignKeyConstraint(
                ["successor_id"],
                ["tasks.id"],
                name=op.f("task_dependencies_successor_id_fkey"),
            ),
            sa.PrimaryKeyConstraint(
                "org_id",
                "predecessor_id",
                "successor_id",
                name=op.f("task_dependencies_pkey"),
            ),
        )
        op.create_index(
            op.f("idx_dep_successor"),
            "task_dependencies",
            ["org_id", "successor_id"],
            unique=False,
        )
        op.create_index(
            op.f("idx_dep_predecessor"),
            "task_dependencies",
            ["org_id", "predecessor_id"],
            unique=False,
        )

        op.create_table(
            "artifacts",
            sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column("org_id", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column("project_id", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column("task_id", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column("uploader_user_id", sa.UUID(), autoincrement=False, nullable=False),
            sa.Column("storage_provider", sa.TEXT(), autoincrement=False, nullable=False),
            sa.Column("bucket", sa.TEXT(), autoincrement=False, nullable=False),
            sa.Column("object_key", sa.TEXT(), autoincrement=False, nullable=False),
            sa.Column("filename", sa.TEXT(), autoincrement=False, nullable=False),
            sa.Column("content_type", sa.TEXT(), autoincrement=False, nullable=False),
            sa.Column("size_bytes", sa.BIGINT(), autoincrement=False, nullable=False),
            sa.Column("sha256", sa.TEXT(), autoincrement=False, nullable=True),
            sa.Column(
                "created_at",
                postgresql.TIMESTAMP(timezone=True),
                server_default=sa.text("now()"),
                autoincrement=False,
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["task_id"],
                ["tasks.id"],
                name=op.f("artifacts_task_id_fkey"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("artifacts_pkey")),
        )
        op.create_index(
            op.f("idx_artifacts_task_time"),
            "artifacts",
            ["org_id", "task_id", sa.literal_column("created_at DESC")],
            unique=False,
        )
        op.create_index(
            op.f("idx_artifacts_object"),
            "artifacts",
            ["org_id", "bucket", "object_key"],
            unique=False,
        )
