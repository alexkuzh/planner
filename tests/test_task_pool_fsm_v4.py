# tests/test_task_pool_fsm_v4.py
"""
Тесты для Pool Architecture (FSM v4).

Покрываемые сценарии:
1. unblock: blocked → available
2. self_assign: available → assigned (pull-model)
3. shift_release: assigned/in_progress → available
4. recall_to_pool: assigned/in_progress → available
5. WIP=1 constraint: executor не может взять вторую задачу
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.task import Task, TaskStatus
from app.models.task_transition import TaskTransition
from app.fsm.task_fsm import TransitionNotAllowed
from app.services.task_transition_service import (
    apply_task_transition,
    VersionConflict,
    IdempotencyConflict,
)

from tests.factories import make_project_template


# ============================================================================
# Helpers
# ============================================================================
def _now():
    return datetime.now(tz=timezone.utc)


def _make_task(
    db: Session,
    *,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
    deliverable_id: UUID | None = None,
    created_by: UUID | None = None,
    status: TaskStatus = TaskStatus.available,  # default = pool ready
    row_version: int = 1,
    title: str = "Test Task",
    description: str | None = None,
    assigned_to: UUID | None = None,
    assigned_at: datetime | None = None,
) -> Task:
    """
    Создаёт задачу в БД.

    Важно:
    - больше НЕ читаем "случайный" project_template из базы
    - если org_id/project_id не переданы — создаём project_template через фабрику
    - соблюдаем DB-инвариант M2:
        assigned/in_progress/submitted -> assigned_to и assigned_at обязаны быть не NULL
        blocked/available -> assigned_to и assigned_at должны быть NULL
    """
    status_value = status.value if isinstance(status, TaskStatus) else str(status)

    # гарантируем проект/орг через реальный FK-источник
    if org_id is None or project_id is None:
        pt = make_project_template(db, org_id=org_id or uuid4(), flush=True)
        org_id = org_id or pt.org_id
        project_id = project_id or pt.project_id

    assert org_id is not None
    assert project_id is not None

    active = status_value in {"assigned", "in_progress", "submitted"}

    if active:
        if assigned_to is None:
            assigned_to = uuid4()
        if assigned_at is None:
            assigned_at = _now()
    else:
        # для blocked/available по M2 эти поля должны быть NULL
        assigned_to = None
        assigned_at = None

    task = Task(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        title=title,
        description=description,
        status=status_value,
        created_by=created_by or uuid4(),
        assigned_to=assigned_to,
        assigned_at=assigned_at,
        row_version=row_version,
    )
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


def _count_transitions(db: Session, org_id: UUID, client_event_id: UUID) -> int:
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
    task = _make_task(db, status=TaskStatus.blocked, row_version=1)
    actor = uuid4()
    client_event_id = uuid4()

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

    t2, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="unblock",
        expected_row_version=1,
        payload={},
        client_event_id=client_event_id,
    )

    assert t2.id == t1.id
    assert t2.status == TaskStatus.available.value
    assert t2.row_version == 2
    assert _count_transitions(db, task.org_id, client_event_id) == 1


# ============================================================================
# 2. SELF_ASSIGN: available → assigned (pull-model)
# ============================================================================
def test_self_assign_from_available_pool(db: Session):
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()

    t, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=executor,
        task_id=task.id,
        action="self_assign",
        expected_row_version=1,
        payload={},
        client_event_id=uuid4(),
    )

    assert t.status == TaskStatus.assigned.value
    assert t.assigned_to == executor
    assert t.assigned_at is not None
    assert t.row_version == 2


def test_self_assign_fails_from_non_available_status(db: Session):
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
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()
    client_event_id = uuid4()

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
# 3. SHIFT_RELEASE: assigned/in_progress → available
# ============================================================================
def test_shift_release_from_assigned_returns_to_pool(db: Session):
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()

    t1, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=executor,
        task_id=task.id, action="self_assign",
        expected_row_version=1, payload={}, client_event_id=uuid4()
    )
    assert t1.status == TaskStatus.assigned.value
    assert t1.assigned_to == executor

    t2, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=uuid4(),
        task_id=task.id, action="shift_release",
        expected_row_version=2, payload={}, client_event_id=uuid4()
    )

    assert t2.status == TaskStatus.available.value
    assert t2.assigned_to is None
    assert t2.assigned_at is None
    assert t2.row_version == 3


def test_shift_release_from_in_progress_returns_to_pool(db: Session):
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()

    apply_task_transition(
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

    t3, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=uuid4(),
        task_id=task.id, action="shift_release",
        expected_row_version=3, payload={}, client_event_id=uuid4()
    )

    assert t3.status == TaskStatus.available.value
    assert t3.assigned_to is None
    assert t3.row_version == 4


def test_shift_release_fails_from_submitted(db: Session):
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()

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

    with pytest.raises(TransitionNotAllowed):
        apply_task_transition(
            db, org_id=task.org_id, actor_user_id=uuid4(),
            task_id=task.id, action="shift_release",
            expected_row_version=4, payload={}, client_event_id=uuid4()
        )


# ============================================================================
# 4. RECALL_TO_POOL: assigned/in_progress → available
# ============================================================================
def test_recall_to_pool_from_assigned(db: Session):
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()
    supervisor = uuid4()

    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=executor,
        task_id=task.id, action="self_assign",
        expected_row_version=1, payload={}, client_event_id=uuid4()
    )

    t2, _ = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=supervisor,
        task_id=task.id, action="recall_to_pool",
        expected_row_version=2, payload={}, client_event_id=uuid4()
    )

    assert t2.status == TaskStatus.available.value
    assert t2.assigned_to is None
    assert t2.row_version == 3


def test_recall_to_pool_from_in_progress(db: Session):
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid4()

    apply_task_transition(db, org_id=task.org_id, actor_user_id=executor,
                         task_id=task.id, action="self_assign",
                         expected_row_version=1, payload={}, client_event_id=uuid4())
    apply_task_transition(db, org_id=task.org_id, actor_user_id=executor,
                         task_id=task.id, action="start",
                         expected_row_version=2, payload={}, client_event_id=uuid4())

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
    executor = uuid4()

    # 🔑 фиксируем один org / project
    pt = make_project_template(db)
    org_id = pt.org_id
    project_id = pt.project_id

    task1 = _make_task(
        db,
        org_id=org_id,
        project_id=project_id,
        status=TaskStatus.available,
        row_version=1,
    )
    t1, _ = apply_task_transition(
        db,
        org_id=org_id,
        actor_user_id=executor,
        task_id=task1.id,
        action="self_assign",
        expected_row_version=1,
        payload={},
        client_event_id=uuid4(),
    )
    assert t1.assigned_to == executor

    task2 = _make_task(
        db,
        org_id=org_id,          # 👈 ТОТ ЖЕ org
        project_id=project_id,  # 👈 ТОТ ЖЕ project
        status=TaskStatus.available,
        row_version=1,
    )

    with pytest.raises(TransitionNotAllowed) as exc:
        apply_task_transition(
            db,
            org_id=org_id,
            actor_user_id=executor,
            task_id=task2.id,
            action="self_assign",
            expected_row_version=1,
            payload={},
            client_event_id=uuid4(),
        )

    assert "wip" in str(exc.value).lower() or "already assigned" in str(exc.value).lower()



def test_self_assign_succeeds_after_task_done(db: Session):
    executor = uuid4()

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

    task2 = _make_task(db, status=TaskStatus.available, row_version=1)
    t2, _ = apply_task_transition(
        db, org_id=task2.org_id, actor_user_id=executor,
        task_id=task2.id, action="self_assign",
        expected_row_version=1, payload={}, client_event_id=uuid4()
    )

    assert t2.assigned_to == executor
