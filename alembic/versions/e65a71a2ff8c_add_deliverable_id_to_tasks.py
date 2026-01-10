from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers...
revision = "e65a71a2ff8c"
down_revision = "36e0d64a058c"


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{name}"}).scalar())


def _col_exists(table: str, col: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name=:t
          AND column_name=:c
        LIMIT 1
    """), {"t": table, "c": col}).first())


def upgrade() -> None:
    # 1) add deliverable_id column if missing
    if _table_exists("tasks") and not _col_exists("tasks", "deliverable_id"):
        op.add_column("tasks", sa.Column("deliverable_id", postgresql.UUID(as_uuid=True), nullable=True))

    # 2) ensure org_id exists (fresh-install safety)
    # IMPORTANT: делаем nullable=True, потому что исторически в этот момент могут быть строки без org_id.
    if _table_exists("tasks") and not _col_exists("tasks", "org_id"):
        op.add_column("tasks", sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True))

    # 3) indexes: prefer composite if org_id exists, else fallback
    if _table_exists("tasks"):
        if _col_exists("tasks", "org_id"):
            op.create_index(
                "ix_tasks_org_deliverable",
                "tasks",
                ["org_id", "deliverable_id"],
                unique=False,
            )
        else:
            op.create_index(
                "ix_tasks_deliverable",
                "tasks",
                ["deliverable_id"],
                unique=False,
            )


def downgrade() -> None:
    # drop indexes (if they exist)
    if _table_exists("tasks"):
        op.drop_index("ix_tasks_org_deliverable", table_name="tasks", if_exists=True)
        op.drop_index("ix_tasks_deliverable", table_name="tasks", if_exists=True)

    # do NOT drop columns here (исторически могло быть сложно и ломко),
    # но если хочешь — можно удалить deliverable_id/org_id только если они были добавлены этой миграцией.
