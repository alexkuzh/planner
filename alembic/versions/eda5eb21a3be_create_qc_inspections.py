"""create qc inspections

Revision ID: eda5eb21a3be
Revises: 1be1c4f1bf06
Create Date: 2026-01-05 21:16:23.190809

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'eda5eb21a3be'
down_revision: Union[str, Sequence[str], None] = '1be1c4f1bf06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qc_inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("deliverable_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("inspector_user_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("result", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_qc_deliverable_time", "qc_inspections", ["deliverable_id", "created_at"])
    op.create_index("ix_qc_org_project_time", "qc_inspections", ["org_id", "project_id", "created_at"])

    op.create_foreign_key(
        "fk_qc_deliverable",
        "qc_inspections",
        "deliverables",
        ["deliverable_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_qc_deliverable", "qc_inspections", type_="foreignkey")
    op.drop_index("ix_qc_org_project_time", table_name="qc_inspections")
    op.drop_index("ix_qc_deliverable_time", table_name="qc_inspections")
    op.drop_table("qc_inspections")