"""create project template nodes

Revision ID: e341fe931dfc
Revises: 54fe417a4bf5
Create Date: 2026-01-08 21:25:46.355310

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e341fe931dfc'
down_revision: Union[str, Sequence[str], None] = '54fe417a4bf5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_template_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        sa.Column("template_version_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("code", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),

        sa.Column("parent_code", sa.String(), nullable=True),

        sa.Column("kind", sa.String(), nullable=False, server_default="production"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_milestone", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_unique_constraint(
        "uq_tpl_nodes_version_code",
        "project_template_nodes",
        ["template_version_id", "code"],
    )

    op.create_index("ix_tpl_nodes_version", "project_template_nodes", ["template_version_id"])
    op.create_index("ix_tpl_nodes_version_parent", "project_template_nodes", ["template_version_id", "parent_code"])

    op.create_foreign_key(
        "fk_tpl_nodes_version",
        "project_template_nodes",
        "project_template_versions",
        ["template_version_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # optional: убрать server_default
    op.alter_column("project_template_nodes", "kind", server_default=None)
    op.alter_column("project_template_nodes", "priority", server_default=None)
    op.alter_column("project_template_nodes", "is_milestone", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_tpl_nodes_version", "project_template_nodes", type_="foreignkey")
    op.drop_index("ix_tpl_nodes_version_parent", table_name="project_template_nodes")
    op.drop_index("ix_tpl_nodes_version", table_name="project_template_nodes")
    op.drop_constraint("uq_tpl_nodes_version_code", "project_template_nodes", type_="unique")
    op.drop_table("project_template_nodes")
