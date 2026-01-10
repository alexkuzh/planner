"""add qc responsible user

Revision ID: ccc7cd883a4b
Revises: eda5eb21a3be
Create Date: 2026-01-05 21:42:49.561314

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ccc7cd883a4b'
down_revision: Union[str, Sequence[str], None] = 'eda5eb21a3be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "qc_inspections",
        sa.Column("responsible_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_index(
        "ix_qc_responsible_time",
        "qc_inspections",
        ["responsible_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_qc_responsible_time", table_name="qc_inspections")
    op.drop_column("qc_inspections", "responsible_user_id")
