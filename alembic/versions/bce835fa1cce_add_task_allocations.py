"""add task allocations

Revision ID: bce835fa1cce
Revises: 1659abca23ef
Create Date: 2026-01-05 19:34:35.100058

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bce835fa1cce'
down_revision: Union[str, Sequence[str], None] = '1659abca23ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "task_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("shift_code", sa.Text(), nullable=False),

        sa.Column("allocated_to", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocated_by", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("note", sa.Text(), nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.UniqueConstraint(
            "task_id", "work_date", "shift_code", "allocated_to",
            name="uq_task_alloc_task_date_shift_user"
        ),
    )

    op.create_index(
        "ix_task_alloc_date_shift",
        "task_allocations",
        ["work_date", "shift_code"],
    )
    op.create_index(
        "ix_task_alloc_task_date",
        "task_allocations",
        ["task_id", "work_date"],
    )
    op.create_index(
        "ix_task_alloc_allocated_to_date",
        "task_allocations",
        ["allocated_to", "work_date"],
    )


def downgrade():
    op.drop_index("ix_task_alloc_allocated_to_date", table_name="task_allocations")
    op.drop_index("ix_task_alloc_task_date", table_name="task_allocations")
    op.drop_index("ix_task_alloc_date_shift", table_name="task_allocations")
    op.drop_table("task_allocations")
