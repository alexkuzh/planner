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


def upgrade() -> None:
    """
    Шаг 1: Мигрировать существующие данные FSM v3 → FSM v4
    Шаг 2: Обновить CHECK constraints
    """
    
    # ====================================================================
    # ШАТОК 1: МИГРИРОВАТЬ ДАННЫЕ
    # ====================================================================
    
    # Маппинг from_status: FSM v3 → FSM v4
    op.execute("""
        UPDATE task_transitions 
        SET from_status = CASE from_status
            WHEN 'new' THEN 'blocked'
            WHEN 'planned' THEN 'available'
            WHEN 'in_review' THEN 'submitted'
            WHEN 'rejected' THEN 'available'
            ELSE from_status
        END
        WHERE from_status IN ('new', 'planned', 'in_review', 'rejected');
    """)
    
    # Маппинг to_status: FSM v3 → FSM v4
    op.execute("""
        UPDATE task_transitions 
        SET to_status = CASE to_status
            WHEN 'new' THEN 'blocked'
            WHEN 'planned' THEN 'available'
            WHEN 'in_review' THEN 'submitted'
            WHEN 'rejected' THEN 'available'
            ELSE to_status
        END
        WHERE to_status IN ('new', 'planned', 'in_review', 'rejected');
    """)
    
    # ====================================================================
    # ШАГ 2: ОБНОВИТЬ CONSTRAINTS
    # ====================================================================
    
    # 2.1. Удалить старые constraints
    op.drop_constraint('ck_task_transitions_from_status_allowed', 'task_transitions', type_='check')
    op.drop_constraint('ck_task_transitions_to_status_allowed', 'task_transitions', type_='check')
    
    # 2.2. Добавить новые constraints с FSM v4
    op.create_check_constraint(
        'ck_task_transitions_from_status_allowed',
        'task_transitions',
        "from_status IN ('blocked', 'available', 'assigned', 'in_progress', 'submitted', 'done', 'canceled')"
    )
    
    op.create_check_constraint(
        'ck_task_transitions_to_status_allowed',
        'task_transitions',
        "to_status IN ('blocked', 'available', 'assigned', 'in_progress', 'submitted', 'done', 'canceled')"
    )


def downgrade() -> None:
    """
    Откат к FSM v3.
    
    ВАЖНО: Downgrade НЕ восстанавливает исходные данные!
    Маппинг FSM v4 → FSM v3:
    - blocked   → new
    - available → planned
    - submitted → in_review
    """
    
    # ====================================================================
    # ШАГ 1: ОТКАТИТЬ ДАННЫЕ
    # ====================================================================
    
    # Reverse mapping from_status: FSM v4 → FSM v3
    op.execute("""
        UPDATE task_transitions 
        SET from_status = CASE from_status
            WHEN 'blocked' THEN 'new'
            WHEN 'available' THEN 'planned'
            WHEN 'submitted' THEN 'in_review'
            ELSE from_status
        END
        WHERE from_status IN ('blocked', 'available', 'submitted');
    """)
    
    # Reverse mapping to_status: FSM v4 → FSM v3
    op.execute("""
        UPDATE task_transitions 
        SET to_status = CASE to_status
            WHEN 'blocked' THEN 'new'
            WHEN 'available' THEN 'planned'
            WHEN 'submitted' THEN 'in_review'
            ELSE to_status
        END
        WHERE to_status IN ('blocked', 'available', 'submitted');
    """)
    
    # ====================================================================
    # ШАГ 2: ОТКАТИТЬ CONSTRAINTS
    # ====================================================================
    
    # 2.1. Удалить FSM v4 constraints
    op.drop_constraint('ck_task_transitions_from_status_allowed', 'task_transitions', type_='check')
    op.drop_constraint('ck_task_transitions_to_status_allowed', 'task_transitions', type_='check')
    
    # 2.2. Восстановить FSM v3 constraints
    op.create_check_constraint(
        'ck_task_transitions_from_status_allowed',
        'task_transitions',
        "from_status IN ('new', 'planned', 'assigned', 'in_progress', 'in_review', 'rejected', 'done', 'canceled')"
    )
    
    op.create_check_constraint(
        'ck_task_transitions_to_status_allowed',
        'task_transitions',
        "to_status IN ('new', 'planned', 'assigned', 'in_progress', 'in_review', 'rejected', 'done', 'canceled')"
    )
