"""create deliverables

Revision ID: 36e0d64a058c
Revises: a0c3334f8837
Create Date: 2026-01-05 20:48:05.293706

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '36e0d64a058c'
down_revision: Union[str, Sequence[str], None] = 'a0c3334f8837'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deliverables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("deliverable_type", sa.String(), nullable=False),
        sa.Column("serial", sa.Text(), nullable=False),

        sa.Column("status", sa.String(), nullable=False, server_default="open"),

        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_unique_constraint(
        "uq_deliverables_org_serial",
        "deliverables",
        ["org_id", "serial"],
    )

    op.create_index("ix_deliverables_org_project", "deliverables", ["org_id", "project_id"])
    op.create_index("ix_deliverables_org_status", "deliverables", ["org_id", "status"])
    op.create_index("ix_deliverables_org_serial", "deliverables", ["org_id", "serial"])

    # optional: уберём server_default, чтобы default был в приложении
    op.alter_column("deliverables", "status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_deliverables_org_serial", table_name="deliverables")
    op.drop_index("ix_deliverables_org_status", table_name="deliverables")
    op.drop_index("ix_deliverables_org_project", table_name="deliverables")
    op.drop_constraint("uq_deliverables_org_serial", "deliverables", type_="unique")
    op.drop_table("deliverables")