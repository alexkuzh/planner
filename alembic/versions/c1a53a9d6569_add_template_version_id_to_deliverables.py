"""add template_version_id to deliverables

Revision ID: c1a53a9d6569
Revises: eaff91734be9
Create Date: 2026-01-08 21:13:20.773264

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c1a53a9d6569'
down_revision: Union[str, Sequence[str], None] = 'eaff91734be9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "deliverables",
        sa.Column("template_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_index(
        "ix_deliverables_template_version",
        "deliverables",
        ["template_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_deliverables_template_version", table_name="deliverables")
    op.drop_column("deliverables", "template_version_id")