"""create deliverable signoffs

Revision ID: 1be1c4f1bf06
Revises: e65a71a2ff8c
Create Date: 2026-01-05 21:03:45.235794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1be1c4f1bf06'
down_revision: Union[str, Sequence[str], None] = 'e65a71a2ff8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deliverable_signoffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("deliverable_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("signed_off_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result", sa.String(), nullable=False, server_default="approved"),
        sa.Column("comment", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_signoffs_deliverable_time", "deliverable_signoffs", ["deliverable_id", "created_at"])
    op.create_index("ix_signoffs_org_project_time", "deliverable_signoffs", ["org_id", "project_id", "created_at"])

    op.create_foreign_key(
        "fk_signoffs_deliverable",
        "deliverable_signoffs",
        "deliverables",
        ["deliverable_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # optional: уберём server_default, чтобы default был в приложении
    op.alter_column("deliverable_signoffs", "result", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_signoffs_deliverable", "deliverable_signoffs", type_="foreignkey")
    op.drop_index("ix_signoffs_org_project_time", table_name="deliverable_signoffs")
    op.drop_index("ix_signoffs_deliverable_time", table_name="deliverable_signoffs")
    op.drop_table("deliverable_signoffs")
