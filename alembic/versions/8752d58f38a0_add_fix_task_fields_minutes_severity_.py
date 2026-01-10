"""add fix task fields minutes_severity_source

Revision ID: 8752d58f38a0
Revises: c0d28c5727c6
Create Date: 2026-01-08 22:48:03.526934
"""
from typing import Sequence, Union, Optional

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "8752d58f38a0"
down_revision: Union[str, Sequence[str], None] = "c0d28c5727c6"
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


def _col_exists(table: str, col: str) -> bool:
    conn = op.get_bind()
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND table_name=:t
                  AND column_name=:c
                LIMIT 1
                """
            ),
            {"t": table, "c": col},
        ).first()
    )


def _udt_name(table: str, col: str) -> Optional[str]:
    conn = op.get_bind()
    return conn.execute(
        text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name=:t
              AND column_name=:c
            LIMIT 1
            """
        ),
        {"t": table, "c": col},
    ).scalar()


def _tasks_id_is_uuid() -> bool:
    return _udt_name("tasks", "id") == "uuid"


def upgrade() -> None:
    # --- enums ---
    fix_severity = postgresql.ENUM("minor", "major", "critical", name="fix_severity")
    fix_source = postgresql.ENUM(
        "qc_reject", "worker_initiative", "supervisor_request", name="fix_source"
    )

    # Create enums (safe)
    bind = op.get_bind()
    fix_severity.create(bind, checkfirst=True)
    fix_source.create(bind, checkfirst=True)

    # --- columns on tasks (safe add) ---
    # NOTE: НЕ трогаем tasks.kind (в проекте это String: production/maintenance/admin/other)
    if not _col_exists("tasks", "origin_task_id"):
        op.add_column(
            "tasks",
            sa.Column("origin_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if not _col_exists("tasks", "qc_inspection_id"):
        op.add_column(
            "tasks",
            sa.Column("qc_inspection_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if not _col_exists("tasks", "minutes_spent"):
        op.add_column("tasks", sa.Column("minutes_spent", sa.Integer(), nullable=True))

    if not _col_exists("tasks", "fix_severity"):
        op.add_column("tasks", sa.Column("fix_severity", fix_severity, nullable=True))

    if not _col_exists("tasks", "fix_source"):
        op.add_column("tasks", sa.Column("fix_source", fix_source, nullable=True))

    # --- FKs (guarded) ---

    # FK origin_task_id -> tasks.id возможен только если tasks.id = UUID
    if _tasks_id_is_uuid():
        op.create_foreign_key(
            "fk_tasks_origin_task_id_tasks",
            "tasks",
            "tasks",
            ["origin_task_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # FK qc_inspection_id -> qc_inspections.id только если таблица существует
    if _table_exists("qc_inspections") and _col_exists("qc_inspections", "id"):
        op.create_foreign_key(
            "fk_tasks_qc_inspection_id_qc_inspections",
            "tasks",
            "qc_inspections",
            ["qc_inspection_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # --- Indexes (guarded) ---
    # deliverable_id + kind — если оба столбца есть
    if _col_exists("tasks", "deliverable_id") and _col_exists("tasks", "kind"):
        op.create_index(
            "ix_tasks_deliverable_kind",
            "tasks",
            ["deliverable_id", "kind"],
        )

    if _col_exists("tasks", "qc_inspection_id"):
        op.create_index("ix_tasks_qc_inspection_id", "tasks", ["qc_inspection_id"])

    if _col_exists("tasks", "origin_task_id"):
        op.create_index("ix_tasks_origin_task_id", "tasks", ["origin_task_id"])

    # --- CHECK ---
    op.create_check_constraint(
        "ck_tasks_minutes_spent_nonneg",
        "tasks",
        "minutes_spent IS NULL OR minutes_spent >= 0",
    )


def downgrade() -> None:
    # reverse CHECK / indexes (safe)
    op.drop_constraint(
        "ck_tasks_minutes_spent_nonneg", "tasks", type_="check", if_exists=True
    )
    op.drop_index("ix_tasks_origin_task_id", table_name="tasks", if_exists=True)
    op.drop_index("ix_tasks_qc_inspection_id", table_name="tasks", if_exists=True)
    op.drop_index("ix_tasks_deliverable_kind", table_name="tasks", if_exists=True)

    # reverse FKs (safe)
    op.drop_constraint(
        "fk_tasks_qc_inspection_id_qc_inspections",
        "tasks",
        type_="foreignkey",
        if_exists=True,
    )
    op.drop_constraint(
        "fk_tasks_origin_task_id_tasks",
        "tasks",
        type_="foreignkey",
        if_exists=True,
    )

    # drop columns (safe-ish: only if exist)
    if _col_exists("tasks", "fix_source"):
        op.drop_column("tasks", "fix_source")
    if _col_exists("tasks", "fix_severity"):
        op.drop_column("tasks", "fix_severity")
    if _col_exists("tasks", "minutes_spent"):
        op.drop_column("tasks", "minutes_spent")
    if _col_exists("tasks", "qc_inspection_id"):
        op.drop_column("tasks", "qc_inspection_id")
    if _col_exists("tasks", "origin_task_id"):
        op.drop_column("tasks", "origin_task_id")

    # drop enums (safe)
    bind = op.get_bind()
    postgresql.ENUM(name="fix_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="fix_severity").drop(bind, checkfirst=True)
