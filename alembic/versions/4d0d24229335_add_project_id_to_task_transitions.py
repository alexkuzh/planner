"""add project_id to task_transitions

Revision ID: 4d0d24229335
Revises: 234cac9b53e9
Create Date: 2026-01-09 22:14:19.610953

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4d0d24229335'
down_revision: Union[str, Sequence[str], None] = '234cac9b53e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("task_transitions")}
    if "project_id" in cols:
        return

    # 1) add nullable column first
    op.add_column("task_transitions", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))

    # 2) backfill from tasks
    op.execute("""
        UPDATE task_transitions tt
        SET project_id = t.project_id
        FROM tasks t
        WHERE t.id = tt.task_id
    """)

    # 3) make it NOT NULL
    op.alter_column("task_transitions", "project_id", nullable=False)

    # 4) optional but usually helpful index for queries by org+project
    op.create_index(
        "idx_task_transitions_org_project_time",
        "task_transitions",
        ["org_id", "project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_task_transitions_org_project_time", table_name="task_transitions")
    op.drop_column("task_transitions", "project_id")
