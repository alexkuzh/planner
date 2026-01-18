"""update task_transitions constraints to FSM v4 with data migration

Revision ID: fsm_v4_data_migration
Revises: 4d0d24229335
Create Date: 2026-01-16 16:00:00.000000

ВАЖНО: Эта миграция:
1. Мигрирует существующие данные FSM v3 → FSM v4
2. Обновляет CHECK constraints для FSM v4

Маппинг статусов FSM v3 → FSM v4:
- new       → blocked
- planned   → available
- in_review → submitted
- rejected  → available (возврат в пул после отклонения)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fsm_v4_data_migration'
down_revision: Union[str, None] = '4d0d24229335'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _drop_transition_status_constraints() -> None:
    # During data migration we may temporarily violate status CHECK constraints.
    # Drop them if present; we will re-create afterwards.
    op.execute("ALTER TABLE task_transitions DROP CONSTRAINT IF EXISTS ck_task_transitions_from_status_allowed;")
    op.execute("ALTER TABLE task_transitions DROP CONSTRAINT IF EXISTS ck_task_transitions_to_status_allowed;")


def _add_transition_status_constraints() -> None:
    # Re-create constraints to match FSM v4 allowed status values.
    # Keep this list consistent with the enum/allowed statuses in your models/migrations.
    op.execute(
        """
        ALTER TABLE task_transitions
        ADD CONSTRAINT ck_task_transitions_from_status_allowed
        CHECK (from_status IN ('blocked','available','assigned','in_progress','submitted','done','cancelled'))
        """
    )
    op.execute(
        """
        ALTER TABLE task_transitions
        ADD CONSTRAINT ck_task_transitions_to_status_allowed
        CHECK (to_status IN ('blocked','available','assigned','in_progress','submitted','done','cancelled'))
        """
    )


def upgrade() -> None:
    # Data migration must be runnable on a fresh DB (planner_test) and on an existing DB (planner).
    # Therefore we temporarily drop CHECK constraints that would block intermediate values.
    _drop_transition_status_constraints()

    # Map legacy statuses to FSM v4 statuses.
    op.execute(
        """
        UPDATE task_transitions
        SET from_status = CASE from_status
            WHEN 'new' THEN 'blocked'
            WHEN 'planned' THEN 'available'
            WHEN 'in_review' THEN 'submitted'
            WHEN 'rejected' THEN 'available'
            ELSE from_status
        END
        WHERE from_status IN ('new','planned','in_review','rejected');
        """
    )

    op.execute(
        """
        UPDATE task_transitions
        SET to_status = CASE to_status
            WHEN 'new' THEN 'blocked'
            WHEN 'planned' THEN 'available'
            WHEN 'in_review' THEN 'submitted'
            WHEN 'rejected' THEN 'available'
            ELSE to_status
        END
        WHERE to_status IN ('new','planned','in_review','rejected');
        """
    )

    # Re-create constraints after data is consistent.
    _add_transition_status_constraints()


def downgrade() -> None:
    # Reverse mapping back to legacy statuses. As with upgrade, drop constraints first to allow intermediate values.
    _drop_transition_status_constraints()

    op.execute(
        """
        UPDATE task_transitions
        SET from_status = CASE from_status
            WHEN 'blocked' THEN 'new'
            WHEN 'available' THEN 'planned'
            WHEN 'submitted' THEN 'in_review'
            ELSE from_status
        END
        WHERE from_status IN ('blocked','available','submitted');
        """
    )

    op.execute(
        """
        UPDATE task_transitions
        SET to_status = CASE to_status
            WHEN 'blocked' THEN 'new'
            WHEN 'available' THEN 'planned'
            WHEN 'submitted' THEN 'in_review'
            ELSE to_status
        END
        WHERE to_status IN ('blocked','available','submitted');
        """
    )

    # Restore legacy constraints (if you had them). If not, you can leave them dropped,
    # but we re-add FSM v4 constraints to keep DB consistent.
    _add_transition_status_constraints()
