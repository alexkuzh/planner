"""add unique org_id+client_event_id to task_transitions

Revision ID: 56dce7ebb756
Revises: 2e1368a6d95c
Create Date: (не важно)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "56dce7ebb756"
down_revision: Union[str, Sequence[str], None] = "2e1368a6d95c"
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


def _constraint_exists(constraint_name: str) -> bool:
    conn = op.get_bind()
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND c.conname = :c
                LIMIT 1
                """
            ),
            {"c": constraint_name},
        ).first()
    )


def upgrade() -> None:
    # В fresh DB эта таблица может отсутствовать (исторически миграции не создавали её).
    # Для MVP/tests: если таблицы нет — пропускаем.
    if not _table_exists("task_transitions"):
        return

    # Чтобы upgrade был идемпотентным при странных состояниях
    if _constraint_exists("uq_task_transitions_org_client_event"):
        return

    op.create_unique_constraint(
        "uq_task_transitions_org_client_event",
        "task_transitions",
        ["org_id", "client_event_id"],
    )


def downgrade() -> None:
    if not _table_exists("task_transitions"):
        return

    op.drop_constraint(
        "uq_task_transitions_org_client_event",
        "task_transitions",
        type_="unique",
        if_exists=True,
    )
