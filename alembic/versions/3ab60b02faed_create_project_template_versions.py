"""create project template versions

Revision ID: 3ab60b02faed
Revises: c1a53a9d6569
Create Date: 2026-01-08 21:18:19.652005

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3ab60b02faed'
down_revision: Union[str, Sequence[str], None] = 'c1a53a9d6569'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_template_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("version", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),

        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_unique_constraint(
        "uq_tpl_versions_org_project_version",
        "project_template_versions",
        ["org_id", "project_id", "version"],
    )

    op.create_index("ix_tpl_versions_org_project_time", "project_template_versions", ["org_id", "project_id", "created_at"])
    op.create_index("ix_tpl_versions_org_project_version", "project_template_versions", ["org_id", "project_id", "version"])


def downgrade() -> None:
    op.drop_index("ix_tpl_versions_org_project_version", table_name="project_template_versions")
    op.drop_index("ix_tpl_versions_org_project_time", table_name="project_template_versions")
    op.drop_constraint("uq_tpl_versions_org_project_version", "project_template_versions", type_="unique")
    op.drop_table("project_template_versions")