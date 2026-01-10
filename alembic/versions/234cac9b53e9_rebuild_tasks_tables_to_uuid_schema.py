"""rebuild tasks tables to uuid schema

Revision ID: 234cac9b53e9
Revises: 67813d8d0326
Create Date: 2026-01-09 21:59:58.964398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '234cac9b53e9'
down_revision: Union[str, Sequence[str], None] = '67813d8d0326'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- enums (если уже есть - не создаст заново) ---
    work_kind = postgresql.ENUM("work", "fix", name="work_kind", create_type=False)
    fix_severity = postgresql.ENUM("minor", "major", "critical", name="fix_severity", create_type=False)
    fix_source = postgresql.ENUM("qc_reject", "worker_initiative", "supervisor_request", name="fix_source", create_type=False)


    #work_kind.create(bind, checkfirst=True)
    #fix_severity.create(bind, checkfirst=True)
    #fix_source.create(bind, checkfirst=True)


    # --- снести таблицы, которые завязаны на tasks ---
    # (в test-db нам ок потерять данные)
    op.drop_table("task_events", if_exists=True)
    op.drop_table("task_allocations", if_exists=True)
    op.drop_table("tasks", if_exists=True)

    # --- пересоздать tasks корректно под текущий ORM ---
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("deliverable_id", postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),

        sa.Column("status", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),

        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("other_kind_label", sa.String(), nullable=True),

        sa.Column("work_kind", work_kind, nullable=False, server_default="work"),
        sa.Column("is_milestone", sa.Boolean(), nullable=False, server_default=sa.text("false")),

        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", postgresql.TIMESTAMP(timezone=True), nullable=True),

        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("fix_reason", sa.Text(), nullable=True),
        sa.Column("origin_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("qc_inspection_id", postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("minutes_spent", sa.Integer(), nullable=True),
        sa.Column("fix_severity", fix_severity, nullable=True),
        sa.Column("fix_source", fix_source, nullable=True),

        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),

        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # FK на саму себя (parent/origin)
    op.create_foreign_key(
        "fk_tasks_parent_task_id_tasks",
        "tasks",
        "tasks",
        ["parent_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tasks_origin_task_id_tasks",
        "tasks",
        "tasks",
        ["origin_task_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # FK на qc_inspections (если таблица есть — у тебя она есть)
    op.create_foreign_key(
        "fk_tasks_qc_inspection_id_qc_inspections",
        "tasks",
        "qc_inspections",
        ["qc_inspection_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # checks / indexes (минимально нужные)
    op.create_check_constraint(
        "ck_tasks_minutes_spent_nonneg",
        "tasks",
        "minutes_spent IS NULL OR minutes_spent >= 0",
    )
    op.create_index("ix_tasks_org_project_status", "tasks", ["org_id", "project_id", "status"])
    op.create_index("ix_tasks_org_parent", "tasks", ["org_id", "parent_task_id"])
    op.create_index("ix_tasks_org_deliverable", "tasks", ["org_id", "deliverable_id"])
    op.create_index("ix_tasks_origin_task_id", "tasks", ["origin_task_id"])
    op.create_index("ix_tasks_qc_inspection_id", "tasks", ["qc_inspection_id"])

    # --- task_events (audit log) ---
    op.create_table(
        "task_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("client_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_foreign_key(
        "task_events_task_id_fkey",
        "task_events",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_task_events_task_time",
        "task_events",
        ["org_id", "task_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_task_events_idempotency",
        "task_events",
        ["org_id", "client_event_id"],
        unique=True,
        postgresql_where=sa.text("client_event_id IS NOT NULL"),
    )

    # --- task_transitions (FSM) ---
    op.create_table(
        "task_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(), nullable=False),
        sa.Column("to_status", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expected_row_version", sa.Integer(), nullable=True),
        sa.Column("result_row_version", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_foreign_key(
        "task_transitions_task_id_fkey",
        "task_transitions",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_task_transitions_task_time",
        "task_transitions",
        ["org_id", "task_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_task_transitions_org_client_event",
        "task_transitions",
        ["org_id", "client_event_id"],
        unique=True,
        postgresql_where=sa.text("client_event_id IS NOT NULL"),
    )

    # --- task_allocations (если твой код их создаёт) ---
    op.create_table(
        "task_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_foreign_key(
        "task_allocations_task_id_fkey",
        "task_allocations",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_task_allocations_task", "task_allocations", ["org_id", "task_id"])


def downgrade() -> None:
    # В тестовой БД downgrade обычно не нужен — но сделаем безопасно
    op.drop_table("task_allocations", if_exists=True)
    op.drop_table("task_transitions", if_exists=True)
    op.drop_table("task_events", if_exists=True)
    op.drop_table("tasks", if_exists=True)
