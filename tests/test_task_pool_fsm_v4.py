# tests/test_task_pool_fsm_v4.py
"""
Тесты для Pool Architecture (FSM v4).

Покрываемые сценарии:
1. unblock: blocked → available
2. self_assign: available → assigned (pull-model)
3. shift_release: assigned/in_progress → available
4. recall_to_pool: assigned/in_progress → available
5. WIP=1 constraint: executor не может взять вторую задачу

Структура БД (tasks):
- status: varchar CHECK (... 'blocked', 'available', 'assigned', 'in_progress', 'submitted', 'done', 'canceled')
- assigned_to: uuid (nullable)
- assigned_at: timestamptz (nullable)
- row_version: int (optimistic lock)

Структура БД (task_transitions):
- from_status, to_status: varchar
- action: varchar
- payload: jsonb
- client_event_id: uuid (idempotency key)
"""

import pytest
from uuid import uuid4, UUID
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from app.models.task import Task, TaskStatus
from app.models.task_transition import TaskTransition
from app.fsm.task_fsm import TransitionNotAllowed
from app.services.task_transition_service import (
    apply_task_transition,
    VersionConflict,
    IdempotencyConflict,
)


# ============================================================================
# Helpers
# ============================================================================

def _pick_existing_project_template(db: Session) -> tuple[UUID, UUID]:
    """Возвращает (org_id, project_id) из существующего project_template."""
    row = db.execute(
        # NB: In current DB schema, tasks.project_id FK references project_templates.project_id
        text("SELECT project_id, org_id FROM project_templates LIMIT 1")
    ).mappings().first()
    if not row:
        raise RuntimeError("project_templates is empty in test DB")
    return UUID(str(row["org_id"])), UUID(str(row["project_id"]))


def _make_task(
    db: Session,
    *,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
    deliverable_id: UUID | None = None,
    created_by: UUID | None = None,
    status: TaskStatus = TaskStatus.available,  # ✅ DEFAULT = available (Pool Architecture)
    row_version: int = 1,
    title: str = "Test Task",
    description: str | None = None,
    assigned_to: UUID | None = None,
) -> Task:
    """
    Создаёт задачу в БД.
    
    По умолчанию status=available (готова к выполнению из пула).
    """
    if org_id is None or project_id is None:
        org_db, pt_id = _pick_existing_project_template(db)
        org_id = org_id or org_db
        project_id = project_id or pt_id

    assert project_id is not None

    task = Task(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        title=title,
        description=description,
        status=status.value if isinstance(status, TaskStatus) else str(status),
        created_by=created_by or uuid4(),
        assigned_to=assigned_to,
        row_version=row_version,
    )
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


def _count_transitions(db: Session, org_id: UUID, client_event_id: UUID) -> int:
    """Считает количество transitions с данным client_event_id."""
    return db.execute(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    ).scalar_one()


# ============================================================================
# 1. UNBLOCK: blocked → available
# ============================================================================

def test_unblock_transitions_blocked_to_available(db: Session):
    """
    КРИТИЧЕСКИЙ ТЕСТ: unblock переводит задачу из blocked в available.
    
    Это ключевой переход для Pool Architecture:
    - blocked = задача заблокирована (зависимости не разрешены)
    - available = задача готова к выполнению (пул)
    """
    task = _make_task(db, status=TaskStatus.blocked, row_version=1)
    actor = uuid4()
    
    t, fix_task = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="unblock",
        expected_row_version=1,
        payload={},
        client_event_id=uuid4(),
    )
    
    assert t.status == TaskStatus.available.value
    assert t.row_version == 2
    assert fix_task is None


def test_unblock_fails_from_non_blocked_status(db: Session):
    """
    unblock разрешён ТОЛЬКО из blocked.
    """
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    
    with pytest.raises(TransitionNotAllowed) as exc:
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=uuid4(),
            task_id=task.id,
            action="unblock",
            expected_row_version=1,
            payload={},
            client_event_id=uuid4(),
        )
    
    assert "not allowed from status 'available'" in str(exc.value).lower()


def test_unblock_idempotency(db: Session):
    """
    Повторный unblock с тем же client_event_id не создаёт дубликата.
    """
    task = _make_task(db, status=TaskStatus.blocked, row_version=1)
    actor = uuid4()
    client_event_id = uuid4()
    
    # Первый вызов
    t1, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="unblock",
        expected_row_version=1,
        payload={},
        client_event_id=client_event_id,
    )
    assert t1.status == TaskStatus.available.value
    assert t1.row_version == 2
    
    # Второй вызов (тот же client_event_id)
    t2, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="unblock",
        expected_row_version=1,  # старая версия
        payload={},
        client_event_id=client_event_id,
    )
    
    # Должен вернуть тот же результат
    assert t2.id == t1.id
    assert t2.status == TaskStatus.available.value
    assert t2.row_version == 2
    
    # Проверяем, что transition не задублировался
    transitions_count = _count_transitions(db, task.org_id, client_event_id)
    assert transitions_count == 1


# ============================================================================
# 2. SELF_ASSIGN: available → assigned (pull-model)
# ============================================================================

def test_self_assign_from_available_pool(db: Session):
    """
    КРИТИЧЕСКИЙ ТЕСТ: self_assign — основа pull-модели.
    
    Работник берёт задачу из пула (available) и становится исполнителем.
    actor_user_id автоматически становится assigned_to.
    """
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()
    
    t, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=executor,
        task_id=task.id,
        action="self_assign",
        expected_row_version=1,
        payload={},  # self_assign не требует assign_to в payload
        client_event_id=uuid4(),
    )
    
    assert t.status == TaskStatus.assigned.value
    assert t.assigned_to == executor  # ✅ actor становится исполнителем
    assert t.assigned_at is not None
    assert t.row_version == 2


def test_self_assign_fails_from_non_available_status(db: Session):
    """
    self_assign разрешён ТОЛЬКО из available (пул).
    """
    task = _make_task(db, status=TaskStatus.blocked, row_version=1)
    
    with pytest.raises(TransitionNotAllowed) as exc:
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=uuid4(),
            task_id=task.id,
            action="self_assign",
            expected_row_version=1,
            payload={},
            client_event_id=uuid4(),
        )
    
    assert "not allowed from status 'blocked'" in str(exc.value).lower()


def test_self_assign_idempotency(db: Session):
    """
    Повторный self_assign с тем же client_event_id возвращает тот же результат.
    """
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()
    client_event_id = uuid4()
    
    # Первый вызов
    t1, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=executor,
        task_id=task.id,
        action="self_assign",
        expected_row_version=1,
        payload={},
        client_event_id=client_event_id,
    )
    
    # Второй вызов
    t2, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=executor,
        task_id=task.id,
        action="self_assign",
        expected_row_version=1,
        payload={},
        client_event_id=client_event_id,
    )
    
    assert t2.id == t1.id
    assert t2.assigned_to == executor
    assert _count_transitions(db, task.org_id, client_event_id) == 1


# ============================================================================
# 3. SHIFT_RELEASE: assigned/in_progress → available (system)
# ============================================================================

def test_shift_release_from_assigned_returns_to_pool(db: Session):
    """
    shift_release возвращает задачу в пул (available) и очищает owner.
    
    Сценарий: конец смены, задача была назначена, но не начата.
    """
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()
    
    # self_assign
    t1, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=executor,
        task_id=task.id, action="self_assign",
        expected_row_version=1, payload={}, client_event_id=uuid4()
    )
    assert t1.status == TaskStatus.assigned.value
    assert t1.assigned_to == executor
    
    # shift_release (system)
    t2, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=uuid4(),  # system actor
        task_id=task.id, action="shift_release",
        expected_row_version=2, payload={}, client_event_id=uuid4()
    )
    
    assert t2.status == TaskStatus.available.value
    assert t2.assigned_to is None  # ✅ owner очищается
    assert t2.assigned_at is None
    assert t2.row_version == 3


def test_shift_release_from_in_progress_returns_to_pool(db: Session):
    """
    shift_release работает и из in_progress (задача была начата, но не завершена).
    """
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()
    
    # self_assign + start
    t1, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=executor,
        task_id=task.id, action="self_assign",
        expected_row_version=1, payload={}, client_event_id=uuid4()
    )
    t2, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=executor,
        task_id=task.id, action="start",
        expected_row_version=2, payload={}, client_event_id=uuid4()
    )
    assert t2.status == TaskStatus.in_progress.value
    
    # shift_release
    t3, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=uuid4(),
        task_id=task.id, action="shift_release",
        expected_row_version=3, payload={}, client_event_id=uuid4()
    )
    
    assert t3.status == TaskStatus.available.value
    assert t3.assigned_to is None
    assert t3.row_version == 4


def test_shift_release_fails_from_submitted(db: Session):
    """
    shift_release НЕ разрешён из submitted (задача уже на проверке).
    """
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()
    
    # Доводим до submitted
    apply_task_transition(db, org_id=task.org_id, actor_user_id=executor,
                         task_id=task.id, action="self_assign",
                         expected_row_version=1, payload={}, client_event_id=uuid4())
    apply_task_transition(db, org_id=task.org_id, actor_user_id=executor,
                         task_id=task.id, action="start",
                         expected_row_version=2, payload={}, client_event_id=uuid4())
    t = apply_task_transition(db, org_id=task.org_id, actor_user_id=executor,
                              task_id=task.id, action="submit",
                              expected_row_version=3, payload={}, client_event_id=uuid4())[0]
    
    assert t.status == TaskStatus.submitted.value
    
    # shift_release должен упасть
    with pytest.raises(TransitionNotAllowed):
        apply_task_transition(
            db, org_id=task.org_id, actor_user_id=uuid4(),
            task_id=task.id, action="shift_release",
            expected_row_version=4, payload={}, client_event_id=uuid4()
        )


# ============================================================================
# 4. RECALL_TO_POOL: assigned/in_progress → available (manual)
# ============================================================================

def test_recall_to_pool_from_assigned(db: Session):
    """
    recall_to_pool — ручной отзыв задачи lead/supervisor.
    
    Отличие от shift_release:
    - shift_release: системный (конец смены)
    - recall_to_pool: ручной (supervisor отзывает задачу у работника)
    """
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()
    supervisor = uuid4()
    
    # self_assign
    t1, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=executor,
        task_id=task.id, action="self_assign",
        expected_row_version=1, payload={}, client_event_id=uuid4()
    )
    
    # recall_to_pool (supervisor)
    t2, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=supervisor,
        task_id=task.id, action="recall_to_pool",
        expected_row_version=2, payload={}, client_event_id=uuid4()
    )
    
    assert t2.status == TaskStatus.available.value
    assert t2.assigned_to is None
    assert t2.row_version == 3


def test_recall_to_pool_from_in_progress(db: Session):
    """
    recall_to_pool работает и из in_progress.
    """
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()
    
    # self_assign + start
    apply_task_transition(db, org_id=task.org_id, actor_user_id=executor,
                         task_id=task.id, action="self_assign",
                         expected_row_version=1, payload={}, client_event_id=uuid4())
    apply_task_transition(db, org_id=task.org_id, actor_user_id=executor,
                         task_id=task.id, action="start",
                         expected_row_version=2, payload={}, client_event_id=uuid4())
    
    # recall_to_pool
    t, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=uuid4(),
        task_id=task.id, action="recall_to_pool",
        expected_row_version=3, payload={}, client_event_id=uuid4()
    )
    
    assert t.status == TaskStatus.available.value
    assert t.assigned_to is None


# ============================================================================
# 5. WIP=1 CONSTRAINT: executor не может взять вторую задачу
# ============================================================================

def test_self_assign_fails_when_wip_limit_exceeded(db: Session):
    """
    КРИТИЧЕСКИЙ ТЕСТ: WIP=1 constraint.
    
    По ARCHITECTURE.md v4:
    "Owner WIP = 1: Исполнитель может быть primary executor только одной активной задачи"
    
    Активные задачи = assigned | in_progress
    """
    executor = uuid4()
    
    # Первая задача — успешно
    task1 = _make_task(db, status=TaskStatus.available, row_version=1)
    t1, _ = apply_task_transition(
        db, org_id=task1.org_id, actor_user_id=executor,
        task_id=task1.id, action="self_assign",
        expected_row_version=1, payload={}, client_event_id=uuid4()
    )
    assert t1.assigned_to == executor
    
    # Вторая задача — должна упасть (WIP=1)
    task2 = _make_task(db, status=TaskStatus.available, row_version=1)
    with pytest.raises(TransitionNotAllowed) as exc:
        apply_task_transition(
            db, org_id=task2.org_id, actor_user_id=executor,
            task_id=task2.id, action="self_assign",
            expected_row_version=1, payload={}, client_event_id=uuid4()
        )
    
    assert "wip" in str(exc.value).lower() or "already assigned" in str(exc.value).lower()


def test_self_assign_succeeds_after_task_done(db: Session):
    """
    После завершения первой задачи (done) можно взять вторую.
    """
    executor = uuid4()
    
    # Первая задача: self_assign → start → submit → review_approve → done
    task1 = _make_task(db, status=TaskStatus.available, row_version=1)
    apply_task_transition(db, org_id=task1.org_id, actor_user_id=executor,
                         task_id=task1.id, action="self_assign",
                         expected_row_version=1, payload={}, client_event_id=uuid4())
    apply_task_transition(db, org_id=task1.org_id, actor_user_id=executor,
                         task_id=task1.id, action="start",
                         expected_row_version=2, payload={}, client_event_id=uuid4())
    apply_task_transition(db, org_id=task1.org_id, actor_user_id=executor,
                         task_id=task1.id, action="submit",
                         expected_row_version=3, payload={}, client_event_id=uuid4())
    t1 = apply_task_transition(db, org_id=task1.org_id, actor_user_id=uuid4(),
                               task_id=task1.id, action="review_approve",
                               expected_row_version=4, payload={}, client_event_id=uuid4())[0]
    
    assert t1.status == TaskStatus.done.value
    
    # Вторая задача — теперь должно пройти (WIP освободился)
    task2 = _make_task(db, status=TaskStatus.available, row_version=1)
    t2, _ = apply_task_transition(
        db, org_id=task2.org_id, actor_user_id=executor,
        task_id=task2.id, action="self_assign",
        expected_row_version=1, payload={}, client_event_id=uuid4()
    )
    
    assert t2.assigned_to == executor
    assert t2.status == TaskStatus.assigned.value


def test_self_assign_succeeds_after_shift_release(db: Session):
    """
    После shift_release первой задачи можно взять вторую.
    """
    executor = uuid4()
    
    # Первая задача: self_assign → shift_release
    task1 = _make_task(db, status=TaskStatus.available, row_version=1)
    apply_task_transition(db, org_id=task1.org_id, actor_user_id=executor,
                         task_id=task1.id, action="self_assign",
                         expected_row_version=1, payload={}, client_event_id=uuid4())
    apply_task_transition(db, org_id=task1.org_id, actor_user_id=uuid4(),
                         task_id=task1.id, action="shift_release",
                         expected_row_version=2, payload={}, client_event_id=uuid4())
    
    # Вторая задача — должно пройти
    task2 = _make_task(db, status=TaskStatus.available, row_version=1)
    t2, _ = apply_task_transition(
        db, org_id=task2.org_id, actor_user_id=executor,
        task_id=task2.id, action="self_assign",
        expected_row_version=1, payload={}, client_event_id=uuid4()
    )
    
    assert t2.assigned_to == executor
