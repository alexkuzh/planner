# tests/test_fsm_transitions.py
"""
FSM transition invariants tests.

Goal:
- verify that transitions are allowed/forbidden exactly as FSM v4 defines
- ensure row_version + idempotency behave correctly
- data must satisfy DB-hardening invariants (M2, FK project_templates)

This file intentionally avoids:
- create_all/drop_all
- programmatic alembic in pytest
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.fsm.task_fsm import TransitionNotAllowed
from app.models.task import Task, TaskStatus
from app.models.task_transition import TaskTransition
from app.services.task_transition_service import apply_task_transition, IdempotencyConflict

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
    created_by: UUID | None = None,
    status: TaskStatus = TaskStatus.blocked,
    row_version: int = 1,
    title: str = "FSM Test Task",
    assigned_to: UUID | None = None,
    assigned_at: datetime | None = None,
) -> Task:
    """
    Make a task that is valid under DB constraints:
    - FK: tasks.project_id -> project_templates.project_id
    - M2: active statuses require assigned_to and assigned_at
    """
    status_value = status.value if isinstance(status, TaskStatus) else str(status)

    if org_id is None or project_id is None:
        pt = make_project_template(db, org_id=org_id or uuid.uuid4(), flush=True)
        org_id = org_id or pt.org_id
        project_id = project_id or pt.project_id

    active = status_value in {"assigned", "in_progress", "submitted"}
    if active:
        if assigned_to is None:
            assigned_to = uuid.uuid4()
        if assigned_at is None:
            assigned_at = _now()
    else:
        assigned_to = None
        assigned_at = None

    t = Task(
        id=uuid.uuid4(),
        org_id=org_id,
        project_id=project_id,
        title=title,
        status=status_value,
        kind="production",
        created_by=created_by or uuid.uuid4(),
        priority=0,
        assigned_to=assigned_to,
        assigned_at=assigned_at,
        row_version=row_version,
    )
    db.add(t)
    db.flush()
    db.refresh(t)
    return t


def _count_transitions(db: Session, org_id: UUID, client_event_id: UUID) -> int:
    return db.execute(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    ).scalar_one()


# ============================================================================
# Invariants (keep these aligned with FSM v4)
# ============================================================================

def test_invariant_cannot_submit_from_new(db: Session):
    t = _make_task(db, status=TaskStatus.blocked, row_version=1)

    with pytest.raises(TransitionNotAllowed):
        apply_task_transition(
            db,
            org_id=t.org_id,
            actor_user_id=uuid.uuid4(),
            task_id=t.id,
            action="submit",
            expected_row_version=1,
            payload={},
            client_event_id=uuid.uuid4(),
        )


def test_invariant_unblock_from_blocked(db: Session):
    t = _make_task(db, status=TaskStatus.blocked, row_version=1)

    t2, _ = apply_task_transition(
        db,
        org_id=t.org_id,
        actor_user_id=uuid.uuid4(),
        task_id=t.id,
        action="unblock",
        expected_row_version=1,
        payload={},
        client_event_id=uuid.uuid4(),
    )
    assert t2.status == TaskStatus.available.value
    assert t2.row_version == 2


def test_invariant_self_assign_from_available(db: Session):
    t = _make_task(db, status=TaskStatus.available, row_version=1)
    executor = uuid.uuid4()

    t2, _ = apply_task_transition(
        db,
        org_id=t.org_id,
        actor_user_id=executor,
        task_id=t.id,
        action="self_assign",
        expected_row_version=1,
        payload={},
        client_event_id=uuid.uuid4(),
    )

    assert t2.status == TaskStatus.assigned.value
    assert t2.assigned_to == executor
    assert t2.assigned_at is not None
    assert t2.row_version == 2


def test_invariant_start_requires_assigned(db: Session):
    t = _make_task(db, status=TaskStatus.available, row_version=1)

    with pytest.raises(TransitionNotAllowed):
        apply_task_transition(
            db,
            org_id=t.org_id,
            actor_user_id=uuid.uuid4(),
            task_id=t.id,
            action="start",
            expected_row_version=1,
            payload={},
            client_event_id=uuid.uuid4(),
        )


def test_invariant_start_from_assigned(db: Session):
    executor = uuid.uuid4()
    t = _make_task(db, status=TaskStatus.assigned, row_version=1, assigned_to=executor)

    t2, _ = apply_task_transition(
        db,
        org_id=t.org_id,
        actor_user_id=executor,
        task_id=t.id,
        action="start",
        expected_row_version=1,
        payload={},
        client_event_id=uuid.uuid4(),
    )

    assert t2.status == TaskStatus.in_progress.value
    assert t2.row_version == 2


def test_invariant_submit_from_in_progress(db: Session):
    executor = uuid.uuid4()
    t = _make_task(db, status=TaskStatus.in_progress, row_version=1, assigned_to=executor)

    t2, _ = apply_task_transition(
        db,
        org_id=t.org_id,
        actor_user_id=executor,
        task_id=t.id,
        action="submit",
        expected_row_version=1,
        payload={},
        client_event_id=uuid.uuid4(),
    )

    assert t2.status == TaskStatus.submitted.value
    assert t2.row_version == 2


def test_idempotency_replay_returns_same_result(db: Session):
    executor = uuid.uuid4()
    t = _make_task(db, status=TaskStatus.available, row_version=1)
    client_event_id = uuid.uuid4()

    t1, _ = apply_task_transition(
        db,
        org_id=t.org_id,
        actor_user_id=executor,
        task_id=t.id,
        action="self_assign",
        expected_row_version=1,
        payload={},
        client_event_id=client_event_id,
    )
    assert t1.status == TaskStatus.assigned.value

    t2, _ = apply_task_transition(
        db,
        org_id=t.org_id,
        actor_user_id=executor,
        task_id=t.id,
        action="self_assign",
        expected_row_version=1,
        payload={},
        client_event_id=client_event_id,
    )

    assert t2.id == t1.id
    assert t2.row_version == t1.row_version
    assert _count_transitions(db, t.org_id, client_event_id) == 1


def test_idempotency_replay_ignores_non_canonical_payload(db: Session):
    executor = uuid.uuid4()
    t = _make_task(db, status=TaskStatus.available, row_version=1)
    client_event_id = uuid.uuid4()

    t1, _ = apply_task_transition(
        db,
        org_id=t.org_id,
        actor_user_id=executor,
        task_id=t.id,
        action="self_assign",
        expected_row_version=1,
        payload={"x": 1},
        client_event_id=client_event_id,
    )

    t2, _ = apply_task_transition(
        db,
        org_id=t.org_id,
        actor_user_id=executor,
        task_id=t.id,
        action="self_assign",
        expected_row_version=1,
        payload={"x": 2},  # ignored by canonicalizer
        client_event_id=client_event_id,
    )

    assert t2.id == t1.id
    assert _count_transitions(db, t.org_id, client_event_id) == 1



def test_row_version_mismatch_rejected_and_state_unchanged(db: Session):
    executor = uuid.uuid4()
    t = _make_task(db, status=TaskStatus.available, row_version=1)

    # first: self_assign ok
    t1, _ = apply_task_transition(
        db,
        org_id=t.org_id,
        actor_user_id=executor,
        task_id=t.id,
        action="self_assign",
        expected_row_version=1,
        payload={},
        client_event_id=uuid.uuid4(),
    )
    assert t1.status == TaskStatus.assigned.value
    assert t1.row_version == 2

    # second: try start with old expected_row_version -> should fail
    with pytest.raises(Exception):
        apply_task_transition(
            db,
            org_id=t.org_id,
            actor_user_id=executor,
            task_id=t.id,
            action="start",
            expected_row_version=1,  # mismatch
            payload={},
            client_event_id=uuid.uuid4(),
        )

    # ensure unchanged
    fresh = db.get(Task, t.id)
    assert fresh is not None
    assert fresh.status == TaskStatus.assigned.value
    assert fresh.row_version == 2
