# tests/test_fsm_transitions.py

import pytest

from uuid import uuid4, UUID
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.task import Task, TaskStatus
from app.models.task_transition import TaskTransition

from app.fsm.task_fsm import TransitionNotAllowed

from app.services.task_transition_service import apply_task_transition, VersionConflict, IdempotencyConflict


def _make_task(
    db,
    *,
    org_id=None,
    project_id=None,
    deliverable_id=None,
    created_by=None,
    status=TaskStatus.new,
    row_version=1,
    title="T",
    description=None,
):
    t = Task(
        id=uuid4(),
        org_id=org_id or uuid4(),
        project_id=project_id or uuid4(),
        deliverable_id=deliverable_id,         # None допустим, но reject->fix-task потребует deliverable_id
        title=title,
        description=description,
        status=status.value if isinstance(status, TaskStatus) else str(status),
        created_by=created_by or uuid4(),      # ОБЯЗАТЕЛЬНОЕ поле
        row_version=row_version,
    )
    db.add(t)
    db.flush()
    db.refresh(t)
    return t

def _count_transitions(db, org_id, client_event_id):
    return db.execute(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    ).scalar_one()


def test_invariant_cannot_submit_from_new(db):
    task = _make_task(db, status=TaskStatus.new, row_version=1)
    actor = uuid4()

    with pytest.raises(TransitionNotAllowed):
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=actor,
            task_id=task.id,
            action="submit",
            expected_row_version=1,
            payload={},
            client_event_id=uuid4(),
        )

    db.refresh(task)
    assert task.status == TaskStatus.new.value
    assert task.row_version == 1


def test_fsm_negative_assign_requires_payload_assign_to(db):
    task = _make_task(db, status=TaskStatus.new, row_version=1)
    actor = uuid4()

    with pytest.raises(TransitionNotAllowed) as e:
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=actor,
            task_id=task.id,
            action="assign",
            expected_row_version=1,
            payload={},  # нет assign_to/user_id
            client_event_id=uuid4(),
        )

    assert "assign" in str(e.value).lower()


def test_row_version_mismatch_rejected_and_state_unchanged(db):
    task = _make_task(db, status=TaskStatus.in_progress, row_version=5)
    actor = uuid4()

    with pytest.raises(VersionConflict) as e:
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=actor,
            task_id=task.id,
            action="submit",          # валидный action из in_progress
            expected_row_version=4,   # неверно
            payload={},
            client_event_id=uuid4(),
        )

    db.refresh(task)
    assert task.status == TaskStatus.in_progress.value
    assert task.row_version == 5
    assert "expected row_version" in str(e.value).lower()


def test_invariant_cannot_assign_from_done(db):
    task = _make_task(db, status=TaskStatus.new, row_version=1)
    actor = uuid4()
    assignee = str(uuid4())

    # new -> assigned
    t1, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="assign",
        expected_row_version=1,
        payload={"assign_to": assignee},
        client_event_id=uuid4(),
    )
    assert t1.status == TaskStatus.assigned.value
    assert t1.row_version == 2

    # assigned -> in_progress
    t2, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="start",
        expected_row_version=2,
        payload={},
        client_event_id=uuid4(),
    )
    assert t2.status == TaskStatus.in_progress.value
    assert t2.row_version == 3

    # in_progress -> in_review
    t3, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="submit",
        expected_row_version=3,
        payload={},
        client_event_id=uuid4(),
    )
    assert t3.status == TaskStatus.in_review.value
    assert t3.row_version == 4

    # in_review -> done (approve)
    t4, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="approve",
        expected_row_version=4,
        payload={},
        client_event_id=uuid4(),
    )
    assert t4.status == TaskStatus.done.value
    assert t4.row_version == 5

    # инвариант: assign из done нельзя
    with pytest.raises(TransitionNotAllowed):
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=actor,
            task_id=task.id,
            action="assign",
            expected_row_version=5,
            payload={"assign_to": str(uuid4())},
            client_event_id=uuid4(),
        )

    db.refresh(task)
    assert task.status == TaskStatus.done.value
    assert task.row_version == 5


def test_reject_allowed_without_reason_when_deliverable_linked(db):
    # ВАЖНО: текущий сервис требует deliverable_id для reject->create_fix_task
    task = _make_task(db, status=TaskStatus.new, row_version=1, deliverable_id=uuid4())
    actor = uuid4()

    # new -> assigned
    t1, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="assign",
        expected_row_version=1,
        payload={"assign_to": str(uuid4())},
        client_event_id=uuid4(),
    )
    assert t1.status == TaskStatus.assigned.value

    # assigned -> in_progress
    t2, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="start",
        expected_row_version=2,
        payload={},
        client_event_id=uuid4(),
    )
    assert t2.status == TaskStatus.in_progress.value

    # in_progress -> in_review
    t3, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="submit",
        expected_row_version=3,
        payload={},
        client_event_id=uuid4(),
    )
    assert t3.status == TaskStatus.in_review.value
    assert t3.row_version == 4

    # in_review -> rejected (даже без reason)
    t4, fix_task = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="reject",
        expected_row_version=4,
        payload={},  # reason пустой - по текущему FSM это ок
        client_event_id=uuid4(),
    )
    assert t4.status == TaskStatus.rejected.value
    assert t4.row_version == 5
    assert fix_task is not None  # т.к. side_effect create_fix_task всегда создаётся


def test_reject_requires_deliverable_link_in_service(db):
    # FSM разрешит reject, но сервис/side-effect запрещает создавать fix-task без deliverable_id
    task = _make_task(db, status=TaskStatus.new, row_version=1, deliverable_id=None)
    actor = uuid4()

    # доводим до in_review
    t1, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="assign",
        expected_row_version=1,
        payload={"assign_to": str(uuid4())},
        client_event_id=uuid4(),
    )
    t2, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="start",
        expected_row_version=2,
        payload={},
        client_event_id=uuid4(),
    )
    t3, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="submit",
        expected_row_version=3,
        payload={},
        client_event_id=uuid4(),
    )
    assert t3.status == TaskStatus.in_review.value
    assert t3.row_version == 4

    with pytest.raises(TransitionNotAllowed) as e:
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=actor,
            task_id=task.id,
            action="reject",
            expected_row_version=4,
            payload={},
            client_event_id=uuid4(),
        )

    # сообщение может отличаться, но обычно там про deliverable
    assert "deliverable" in str(e.value).lower()


def test_idempotency_same_client_event_id_no_duplicate_transition(db):
    task = _make_task(db, status=TaskStatus.new, row_version=1)
    actor = uuid4()
    assignee = str(uuid4())
    client_event_id = uuid4()

    # 1st call (should apply transition)
    t1, fix1 = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="assign",
        expected_row_version=1,
        payload={"assign_to": assignee},
        client_event_id=client_event_id,
    )
    assert fix1 is None
    assert t1.status == TaskStatus.assigned.value
    assert t1.row_version == 2

    # transitions count after first call
    n1 = db.scalar(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == task.org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    )
    assert n1 == 1

    # 2nd call with SAME client_event_id (must be idempotent / no-op)
    t2, fix2 = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="assign",
        expected_row_version=1,  # retry typically sends the same expected version
        payload={"assign_to": assignee},
        client_event_id=client_event_id,
    )
    assert fix2 is None

    # must not change anything on second identical call
    assert t2.id == t1.id
    assert t2.status == t1.status
    assert t2.row_version == t1.row_version

    # transitions count must remain 1 (no duplicates)
    n2 = db.scalar(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == task.org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    )
    assert n2 == 1


def test_idempotency_same_client_event_id_but_different_payload_is_rejected(db):
    # arrange
    task = _make_task(db, status=TaskStatus.new, row_version=1)
    actor = uuid4()
    client_event_id = uuid4()

    assign_to_1 = str(uuid4())
    assign_to_2 = str(uuid4())

    # act 1: first call ok
    t1, fix1 = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="assign",
        expected_row_version=1,
        payload={"assign_to": assign_to_1},
        client_event_id=client_event_id,
    )
    assert fix1 is None
    assert t1.row_version == 2

    transitions_before = _count_transitions(db, task.org_id, client_event_id)
    assert transitions_before == 1

    # act 2: same client_event_id but DIFFERENT payload -> strict conflict
    with pytest.raises(IdempotencyConflict):
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=actor,
            task_id=task.id,
            action="assign",
            expected_row_version=1,  # даже если тот же expected_row_version
            payload={"assign_to": assign_to_2},  # mismatch here
            client_event_id=client_event_id,
        )

    # assert: no changes
    db.refresh(task)
    assert task.row_version == 2  # осталось как после первого вызова
    assert str(task.assigned_to) == assign_to_1  # не перезаписалось

    transitions_after = _count_transitions(db, task.org_id, client_event_id)
    assert transitions_after == 1  # не задублилось


def test_idempotency_race_unique_violation_returns_existing(db, monkeypatch, SessionLocal):
    """
    Race simulation (без зависаний и без commit внутри фикстуры db):
    - task создаём и COMMIT'им в отдельной сессии (чтобы FK не блокировал конкурентную вставку)
    - в момент db.flush() конкурентная транзакция вставляет task_transition и commit
    - основной flush ловит unique violation
    - сервис должен отработать idempotency и вернуть existing
    """

    from uuid import uuid4
    from datetime import datetime, timezone
    from sqlalchemy import text, select, func
    from sqlalchemy.orm import Session

    actor = uuid4()
    assignee = str(uuid4())
    client_event_id = uuid4()

    # --- setup in separate committed session (чтобы FK не висел) ---
    with SessionLocal() as s_setup:
        task = _make_task(s_setup, status=TaskStatus.new, row_version=1)
        task_id = task.id
        org_id = task.org_id
        project_id = task.project_id
        s_setup.commit()

    original_flush = db.flush
    injected = {"done": False}

    def flush_with_race(*args, **kwargs):
        if not injected["done"]:
            injected["done"] = True

            # конкурентная вставка в отдельной транзакции
            engine = db.get_bind()
            with Session(bind=engine) as s2:
                now = datetime.now(timezone.utc)
                s2.execute(
                    text(
                        """
                        INSERT INTO task_transitions
                          (id, org_id, project_id, task_id,
                           actor_user_id, action, from_status, to_status,
                           payload, client_event_id, created_at,
                           expected_row_version, result_row_version)
                        VALUES
                          (:id, :org_id, :project_id, :task_id,
                           :actor_user_id, :action, :from_status, :to_status,
                           CAST(:payload AS jsonb), :client_event_id, :created_at,
                           :expected_row_version, :result_row_version)
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "task_id": str(task_id),
                        "actor_user_id": str(actor),
                        "action": "assign",
                        "from_status": TaskStatus.new.value,
                        "to_status": TaskStatus.assigned.value,
                        "payload": f'{{"assign_to":"{assignee}"}}',
                        "client_event_id": str(client_event_id),
                        "created_at": now,
                        "expected_row_version": 1,
                        "result_row_version": 2,
                    },
                )
                s2.commit()

        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", flush_with_race)

    try:
        returned_task, fix_task = apply_task_transition(
            db,
            org_id=org_id,
            actor_user_id=actor,
            task_id=task_id,
            action="assign",
            expected_row_version=1,
            payload={"assign_to": assignee},
            client_event_id=client_event_id,
        )

        assert fix_task is None

        with SessionLocal() as s_check:
            n = s_check.scalar(
                select(func.count(TaskTransition.id)).where(
                    TaskTransition.org_id == org_id,
                    TaskTransition.client_event_id == client_event_id,
                )
            )
            assert n == 1
        assert returned_task.id == task_id

    finally:
        # cleanup: конкурентная вставка была COMMIT'нута, чистим БД
        engine = db.get_bind()
        with Session(bind=engine) as s_cleanup:
            s_cleanup.execute(
                text(
                    "DELETE FROM task_transitions WHERE org_id = :org AND client_event_id = :ceid"
                ),
                {"org": str(org_id), "ceid": str(client_event_id)},
            )
            s_cleanup.execute(
                text("DELETE FROM tasks WHERE org_id = :org AND id = :tid"),
                {"org": str(org_id), "tid": str(task_id)},
            )
            s_cleanup.commit()





