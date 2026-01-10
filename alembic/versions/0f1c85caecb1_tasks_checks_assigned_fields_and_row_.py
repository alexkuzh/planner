"""tasks checks: assigned fields and row_version

Revision ID: 0f1c85caecb1
Revises: 4d0d24229335
Create Date: 2026-01-10 13:13:22.060041

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f1c85caecb1'
down_revision: Union[str, Sequence[str], None] = '4d0d24229335'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Железная целостность: assigned_to и assigned_at должны быть согласованы.
    #    Либо оба NULL (не назначено), либо оба NOT NULL (назначено + есть timestamp).
    op.create_check_constraint(
        "ck_tasks_assigned_fields_consistent",
        "tasks",
        "(assigned_to IS NULL AND assigned_at IS NULL) OR (assigned_to IS NOT NULL AND assigned_at IS NOT NULL)",
    )

    # 2) Железная целостность: row_version никогда не должен быть меньше 1.
    op.create_check_constraint(
        "ck_tasks_row_version_ge_1",
        "tasks",
        "row_version >= 1",
    )


def downgrade() -> None:
    # Откат должен быть симметричным: удаляем CHECK-и в обратном порядке.
    op.drop_constraint("ck_tasks_row_version_ge_1", "tasks", type_="check")
    op.drop_constraint("ck_tasks_assigned_fields_consistent", "tasks", type_="check")
