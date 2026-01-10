# tests/test_fsm_transitions.py

import pytest

from uuid import uuid4, UUID
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.task import Task, TaskStatus, FixSeverity
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
    Race simulation without patching flush (no hangs):
    - apply_task_transition does:
        1) idempotency SELECT -> sees nothing
        2) tries INSERT .. ON CONFLICT DO NOTHING
    - right before that INSERT we inject a competing row in another transaction
    - our INSERT returns no row (conflict) and service must load/return existing
    """
    from uuid import uuid4
    from datetime import datetime, timezone
    from sqlalchemy import text, select, func

    actor = uuid4()
    assignee = str(uuid4())
    client_event_id = uuid4()

    # create task in separate committed session so FK is not blocked
    with SessionLocal() as s_setup:
        task = _make_task(s_setup, status=TaskStatus.new, row_version=1)
        task_id = task.id
        org_id = task.org_id
        project_id = task.project_id
        s_setup.commit()

    injected = {"done": False}
    original_execute = db.execute

    def execute_with_race(stmt, *args, **kwargs):
        # We only want to inject once, and only right before INSERT into task_transitions.
        if not injected["done"]:
            stmt_str = str(stmt)
            if "INSERT INTO task_transitions" in stmt_str:
                injected["done"] = True

                # competing insert in another transaction
                with SessionLocal() as s2:
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

        return original_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(db, "execute", execute_with_race)

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

    n = db.scalar(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    )
    assert n == 1
    assert returned_task.id == task_id


def test_idempotency_reject_same_client_event_id_does_not_duplicate_fix_task(db):
    """
    Файл: tests/test_fsm_transitions.py

    Проверяем, что reject идемпотентен:
    - первый reject создаёт fix-task и пишет transition (client_event_id)
    - повтор того же reject с тем же client_event_id:
        * НЕ создаёт новый fix-task
        * НЕ добавляет второй transition
        * НЕ меняет row_version задачи
        * возвращает тот же fix_task_id
    """
    actor = uuid4()
    client_event_id = uuid4()

    # ВАЖНО: deliverable_id обязателен, иначе сервис запретит create_fix_task
    task = _make_task(db, status=TaskStatus.new, row_version=1, deliverable_id=uuid4())

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

    # --- act #1: reject (creates fix task) ---
    t4, fix1 = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="reject",
        expected_row_version=4,
        payload={},  # reason optional by current FSM
        client_event_id=client_event_id,
    )
    assert t4.status == TaskStatus.rejected.value
    assert t4.row_version == 5
    assert fix1 is not None
    fix1_id = fix1.id

    # transition count after first reject
    n1 = db.scalar(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == task.org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    )
    assert n1 == 1

    # --- act #2: same reject повтор (idempotent) ---
    t5, fix2 = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="reject",
        expected_row_version=4,   # retry often повторяет тот же expected_row_version
        payload={},
        client_event_id=client_event_id,
    )

    # ничего не должно измениться
    assert t5.id == t4.id
    assert t5.status == t4.status
    assert t5.row_version == t4.row_version  # must stay 5
    assert fix2 is not None
    assert fix2.id == fix1_id  # тот же fix-task

    # transition count must remain 1
    n2 = db.scalar(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == task.org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    )
    assert n2 == 1

    # sanity: в таблице tasks fix-task тоже один (по id)
    # (не обязательно, но полезно)
    assert db.get(Task, fix1_id) is not None


def test_idempotency_reject_same_client_event_id_different_payload_conflict(db):
    """
    Файл: tests/test_fsm_transitions.py

    Строгая идемпотентность:
    тот же client_event_id, но payload другой => IdempotencyConflict.
    """
    actor = uuid4()
    client_event_id = uuid4()

    task = _make_task(db, status=TaskStatus.new, row_version=1, deliverable_id=uuid4())

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

    # act #1: reject payload A
    t4, fix1 = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="reject",
        expected_row_version=4,
        payload={"reason": "A"},  # payload A
        client_event_id=client_event_id,
    )
    assert t4.status == TaskStatus.rejected.value
    assert t4.row_version == 5
    assert fix1 is not None

    # act #2: same client_event_id, payload B => conflict
    with pytest.raises(IdempotencyConflict):
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=actor,
            task_id=task.id,
            action="reject",
            expected_row_version=4,
            payload={"reason": "B"},  # payload mismatch
            client_event_id=client_event_id,
        )

    # assert: transition count still 1
    n = db.scalar(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == task.org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    )
    assert n == 1

    # assert: task unchanged после конфликта
    db.refresh(task)
    assert task.status == TaskStatus.rejected.value
    assert task.row_version == 5


def test_idempotency_reject_same_client_event_id_but_different_reason_is_conflict(db):
    """
    STRICT IDEMPOTENCY TEST (reject):

    Если client_event_id тот же, но payload отличается
    (например, reason / fix_title / severity),
    сервис ОБЯЗАН выбросить IdempotencyConflict.

    ВАЖНО:
    - не создаётся второй fix-task
    - состояние задачи не меняется
    - row_version не увеличивается
    """

    from uuid import uuid4
    from sqlalchemy import select, func

    actor = uuid4()
    client_event_id = uuid4()

    # reject -> create_fix_task требует deliverable_id
    task = _make_task(
        db,
        status=TaskStatus.new,
        row_version=1,
        deliverable_id=uuid4(),
    )

    # --- доводим задачу до in_review ---
    apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="assign",
        expected_row_version=1,
        payload={"assign_to": str(uuid4())},
        client_event_id=uuid4(),
    )

    apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="start",
        expected_row_version=2,
        payload={},
        client_event_id=uuid4(),
    )

    apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="submit",
        expected_row_version=3,
        payload={},
        client_event_id=uuid4(),
    )

    db.refresh(task)
    assert task.status == TaskStatus.in_review.value
    assert task.row_version == 4

    # --- act 1: первый reject ---
    t1, fix1 = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="reject",
        expected_row_version=4,
        payload={"reason": "bad quality"},
        client_event_id=client_event_id,
    )

    assert t1.status == TaskStatus.rejected.value
    assert fix1 is not None

    fix_task_id = fix1.id
    row_version_after_first = t1.row_version

    # --- act 2: reject с ТЕМ ЖЕ client_event_id, но ДРУГОЙ reason ---
    with pytest.raises(IdempotencyConflict):
        apply_task_transition(
            db,
            org_id=task.org_id,
            actor_user_id=actor,
            task_id=task.id,
            action="reject",
            expected_row_version=4,
            payload={"reason": "wrong dimensions"},  # <-- отличие здесь
            client_event_id=client_event_id,
        )

    # --- assert: ничего не изменилось ---
    db.refresh(task)
    assert task.status == TaskStatus.rejected.value
    assert task.row_version == row_version_after_first

    # fix-task не задублился
    fix_tasks = db.scalar(
        select(func.count(Task.id)).where(
            Task.origin_task_id == task.id
        )
    )
    assert fix_tasks == 1

    # transition тоже не задублился
    transitions = db.scalar(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == task.org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    )
    assert transitions == 1


def test_idempotency_reject_same_client_event_id_but_different_fix_title_is_conflict(db):
    """
    STRICT IDEMPOTENCY TEST (reject):
    same client_event_id, but payload differs by fix_title -> IdempotencyConflict.

    ВАЖНО:
    - не создаётся второй fix-task
    - row_version не увеличивается
    - transition не дублируется
    """
    from uuid import uuid4
    from sqlalchemy import select, func

    actor = uuid4()
    client_event_id = uuid4()

    # reject -> fix-task requires deliverable_id
    task = _make_task(db, status=TaskStatus.new, row_version=1, deliverable_id=uuid4())

    # доводим до in_review
    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="assign", expected_row_version=1,
        payload={"assign_to": str(uuid4())}, client_event_id=uuid4(),
    )
    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="start", expected_row_version=2,
        payload={}, client_event_id=uuid4(),
    )
    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="submit", expected_row_version=3,
        payload={}, client_event_id=uuid4(),
    )

    db.refresh(task)
    assert task.status == TaskStatus.in_review.value
    assert task.row_version == 4

    # act1: first reject
    t1, fix1 = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="reject", expected_row_version=4,
        payload={"fix_title": "Fix A"}, client_event_id=client_event_id,
    )
    assert t1.status == TaskStatus.rejected.value
    assert fix1 is not None
    row_version_after_first = t1.row_version

    # act2: same client_event_id but different fix_title -> conflict
    with pytest.raises(IdempotencyConflict):
        apply_task_transition(
            db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
            action="reject", expected_row_version=4,
            payload={"fix_title": "Fix B"},  # <-- mismatch here
            client_event_id=client_event_id,
        )

    # assert: no additional side effects
    db.refresh(task)
    assert task.status == TaskStatus.rejected.value
    assert task.row_version == row_version_after_first

    # only 1 fix-task for origin_task_id
    fix_tasks = db.scalar(
        select(func.count(Task.id)).where(Task.origin_task_id == task.id)
    )
    assert fix_tasks == 1

    # only 1 transition for client_event_id
    transitions = db.scalar(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == task.org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    )
    assert transitions == 1


def test_idempotency_reject_same_client_event_id_but_different_severity_is_conflict(db):
    """
    STRICT IDEMPOTENCY TEST (reject):
    same client_event_id, but payload differs by severity -> IdempotencyConflict.

    ВАЖНО:
    - payload.severity считается частью "fingerprint"
    - не создаётся второй fix-task
    - row_version не увеличивается
    """
    from uuid import uuid4
    from sqlalchemy import select, func

    actor = uuid4()
    client_event_id = uuid4()

    task = _make_task(db, status=TaskStatus.new, row_version=1, deliverable_id=uuid4())

    # доводим до in_review
    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="assign", expected_row_version=1,
        payload={"assign_to": str(uuid4())}, client_event_id=uuid4(),
    )
    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="start", expected_row_version=2,
        payload={}, client_event_id=uuid4(),
    )
    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="submit", expected_row_version=3,
        payload={}, client_event_id=uuid4(),
    )

    db.refresh(task)
    assert task.status == TaskStatus.in_review.value
    assert task.row_version == 4

    # act1: first reject
    t1, fix1 = apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="reject", expected_row_version=4,
        payload={"severity": "major"}, client_event_id=client_event_id,
    )
    assert t1.status == TaskStatus.rejected.value
    assert fix1 is not None
    row_version_after_first = t1.row_version

    # act2: same client_event_id but different severity -> conflict
    with pytest.raises(IdempotencyConflict):
        apply_task_transition(
            db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
            action="reject", expected_row_version=4,
            payload={"severity": "critical"},  # <-- mismatch here
            client_event_id=client_event_id,
        )

    # assert: no additional side effects
    db.refresh(task)
    assert task.status == TaskStatus.rejected.value
    assert task.row_version == row_version_after_first

    fix_tasks = db.scalar(
        select(func.count(Task.id)).where(Task.origin_task_id == task.id)
    )
    assert fix_tasks == 1

    transitions = db.scalar(
        select(func.count(TaskTransition.id)).where(
            TaskTransition.org_id == task.org_id,
            TaskTransition.client_event_id == client_event_id,
        )
    )
    assert transitions == 1


def test_idempotency_reject_severity_enum_vs_string_is_same_request(db):
    """
    Проверяем семантическую эквивалентность payload:
    severity=FixSeverity.major и severity="major" должны считаться одним запросом.
    """
    task = _make_task(db, status=TaskStatus.new, row_version=1, deliverable_id=uuid4())
    actor = uuid4()
    client_event_id = uuid4()

    # доводим до in_review
    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="assign", expected_row_version=1,
        payload={"assign_to": str(uuid4())}, client_event_id=uuid4(),
    )
    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="start", expected_row_version=2,
        payload={}, client_event_id=uuid4(),
    )
    apply_task_transition(
        db, org_id=task.org_id, actor_user_id=actor, task_id=task.id,
        action="submit", expected_row_version=3,
        payload={}, client_event_id=uuid4(),
    )

    # 1) reject with enum severity
    t1, fix1 = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="reject",
        expected_row_version=4,
        payload={"reason": "bad", "severity": FixSeverity.major},
        client_event_id=client_event_id,
    )
    assert t1.status == TaskStatus.rejected.value
    assert fix1 is not None

    # 2) replay same client_event_id but severity as string
    t2, fix2 = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="reject",
        expected_row_version=4,
        payload={"reason": "bad", "severity": "major"},
        client_event_id=client_event_id,
    )

    # idempotent: same fix-task, no duplicates
    assert str(fix2.id) == str(fix1.id)

    n = _count_transitions(db, task.org_id, client_event_id)
    assert n == 1


def test_idempotency_assign_uuid_vs_string_is_same_request(db):
    """
    assign_to: UUID(...) и str(UUID) должны считаться одним запросом для idempotency.
    """
    task = _make_task(db, status=TaskStatus.new, row_version=1)
    actor = uuid4()
    client_event_id = uuid4()

    assignee_uuid = uuid4()

    # 1) first call sends UUID
    t1, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="assign",
        expected_row_version=1,
        payload={"assign_to": assignee_uuid},
        client_event_id=client_event_id,
    )
    assert t1.status == TaskStatus.assigned.value

    # 2) replay sends string
    t2, _ = apply_task_transition(
        db,
        org_id=task.org_id,
        actor_user_id=actor,
        task_id=task.id,
        action="assign",
        expected_row_version=1,
        payload={"assign_to": str(assignee_uuid)},
        client_event_id=client_event_id,
    )

    assert t2.row_version == t1.row_version  # no-op replay
    n = _count_transitions(db, task.org_id, client_event_id)
    assert n == 1