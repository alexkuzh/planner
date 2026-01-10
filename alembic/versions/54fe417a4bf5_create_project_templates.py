"""create project templates

Revision ID: 54fe417a4bf5
Revises: 3ab60b02faed
Create Date: 2026-01-08 21:21:42.298020

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '54fe417a4bf5'
down_revision: Union[str, Sequence[str], None] = '3ab60b02faed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "project_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),

        sa.Column("active_template_version_id", postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_project_templates_org_project", "project_templates", ["org_id", "project_id"])

    op.create_foreign_key(
        "fk_project_templates_active_version",
        "project_templates",
        "project_template_versions",
        ["active_template_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_project_templates_active_version", "project_templates", type_="foreignkey")
    op.drop_index("ix_project_templates_org_project", table_name="project_templates")
    op.drop_table("project_templates")
