"""create project template edges

Revision ID: c0d28c5727c6
Revises: e341fe931dfc
Create Date: 2026-01-08 21:31:40.507823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c0d28c5727c6'
down_revision: Union[str, Sequence[str], None] = 'e341fe931dfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_template_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        sa.Column("template_version_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("predecessor_code", sa.String(), nullable=False),
        sa.Column("successor_code", sa.String(), nullable=False),
    )

    op.create_unique_constraint(
        "uq_tpl_edges_version_pred_succ",
        "project_template_edges",
        ["template_version_id", "predecessor_code", "successor_code"],
    )

    op.create_index("ix_tpl_edges_version", "project_template_edges", ["template_version_id"])
    op.create_index("ix_tpl_edges_version_succ", "project_template_edges", ["template_version_id", "successor_code"])
    op.create_index("ix_tpl_edges_version_pred", "project_template_edges", ["template_version_id", "predecessor_code"])

    op.create_foreign_key(
        "fk_tpl_edges_version",
        "project_template_edges",
        "project_template_versions",
        ["template_version_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tpl_edges_version", "project_template_edges", type_="foreignkey")
    op.drop_index("ix_tpl_edges_version_pred", table_name="project_template_edges")
    op.drop_index("ix_tpl_edges_version_succ", table_name="project_template_edges")
    op.drop_index("ix_tpl_edges_version", table_name="project_template_edges")
    op.drop_constraint("uq_tpl_edges_version_pred_succ", "project_template_edges", type_="unique")
    op.drop_table("project_template_edges")