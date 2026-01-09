# app/services/task_transition_service.py
from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.task import Task, TaskStatus
from app.models.task_transition import TaskTransition
from app.fsm.task_fsm import apply_transition, TransitionNotAllowed

FIX_EFFECT_CREATE = "create_fix_task"

class VersionConflict(Exception):
    pass


def _now():
    return datetime.now(timezone.utc)


def apply_task_transition(
    db: Session,
    *,
    org_id: UUID,
    actor_user_id: UUID,
    task_id: UUID,
    action: str,
    expected_row_version: int,
    payload: dict,
    client_event_id: UUID | None,
) -> tuple[Task, Task | None]:
    """
    Returns (updated_task, created_fix_task_or_none).
    Must be called inside a transaction.
    """

    payload = payload or {}

    # 0) Idempotency fast-path (если этот client_event_id уже применяли — вернуть результат)
    if client_event_id is not None:
        existing = db.execute(
            select(TaskTransition).where(
                TaskTransition.org_id == org_id,
                TaskTransition.client_event_id == client_event_id,
            )
        ).scalar_one_or_none()

        if existing is not None:
            # Вернём актуальное состояние задачи.
            task = db.execute(
                select(Task).where(Task.org_id == org_id, Task.id == existing.task_id)
            ).scalar_one()

            fix_task = None
            # Если это был reject и создали fix-task, он либо лежит как дочерняя по parent_task_id,
            # либо id лежит в payload связующего события.
            # Самый простой MVP: найти последнюю fix-task по parent_task_id.
            fix_task = None
            if existing.payload and "fix_task_id" in existing.payload:
                fix_task = db.get(Task, UUID(existing.payload["fix_task_id"]))

            return task, fix_task

    # 1) Lock task row
    task: Task | None = db.execute(
        select(Task).where(Task.org_id == org_id, Task.id == task_id).with_for_update()
    ).scalar_one_or_none()

    if task is None:
        raise KeyError("Task not found")

    # 2) Optimistic lock
    if task.row_version != expected_row_version:
        raise VersionConflict(f"Expected row_version={expected_row_version}, actual={task.row_version}")

    from_status = TaskStatus(task.status) if isinstance(task.status, str) else task.status

    # 3) FSM
    to_status, side_effects = apply_transition(from_status, action, payload=payload)

    # 3.1) Apply action-specific fields (assignment, etc.)
    if action == "assign":
        assign_to = payload.get("assign_to") or payload.get("user_id")
        if not assign_to:
            raise TransitionNotAllowed("Action 'assign' требует payload.assign_to (user_id).")
        task.assigned_to = UUID(str(assign_to))
        task.assigned_at = _now()

    elif action == "unassign":
        task.assigned_to = None
        task.assigned_at = None

    # 4) Update task status/version
    task.status = to_status.value
    task.updated_at = _now()
    task.row_version += 1

    # 5) Write transition
    tr = TaskTransition(
        id=uuid4(),
        org_id=org_id,
        project_id=task.project_id,
        task_id=task.id,
        actor_user_id=actor_user_id,
        action=action,
        from_status=from_status.value,
        to_status=to_status.value,
        payload=payload,
        client_event_id=client_event_id,
        created_at=_now(),
    )
    db.add(tr)

    fix_task: Task | None = None

    # 6) Side effects (reject => create fix-task)
    for eff in side_effects:
        if eff.kind == FIX_EFFECT_CREATE:
            reason = (eff.payload.get("reason") or "").strip()
            fix_title = (eff.payload.get("fix_title") or "").strip()
            assign_to = eff.payload.get("assign_to")

            fix_task = Task(
                id=uuid4(),
                org_id=org_id,
                project_id=task.project_id,
                title=fix_title or f"Fix: {task.title}",
                description=None,
                status=TaskStatus.planned.value,
                priority=task.priority,
                created_by=actor_user_id,
                assigned_to=UUID(str(assign_to)) if assign_to else None,
                assigned_at=_now() if assign_to else None,
                parent_task_id=task.id,
                fix_reason=reason or "Rejected",
                created_at=_now(),
                updated_at=_now(),
                row_version=1,
            )
            db.add(fix_task)

            # transition for fix-task creation
            fix_tr = TaskTransition(
                id=uuid4(),
                org_id=org_id,
                project_id=task.project_id,
                task_id=fix_task.id,
                actor_user_id=actor_user_id,
                action="create_fix_task",
                from_status=TaskStatus.planned.value,
                to_status=TaskStatus.planned.value,
                payload={"parent_task_id": str(task.id), "reason": reason},
                client_event_id=None,
                created_at=_now(),
            )
            db.add(fix_tr)

            # link transition on original
            link_tr = TaskTransition(
                id=uuid4(),
                org_id=org_id,
                project_id=task.project_id,
                task_id=task.id,
                actor_user_id=actor_user_id,
                action="fix_task_created",
                from_status=to_status.value,
                to_status=to_status.value,
                payload={"fix_task_id": str(fix_task.id)},
                client_event_id=None,
                created_at=_now(),
            )
            db.add(link_tr)

    # 7) Flush (ловим ошибки сразу)
    try:
        db.flush()
    except IntegrityError:
        # Если здесь сработало unique(org_id, client_event_id), значит гонка/повтор.
        # В MVP просто перечитаем по client_event_id и вернём состояние.
        if client_event_id is not None:
            existing = db.execute(
                select(TaskTransition).where(
                    TaskTransition.org_id == org_id,
                    TaskTransition.client_event_id == client_event_id,
                )
            ).scalar_one()
            task = db.execute(select(Task).where(Task.org_id == org_id, Task.id == existing.task_id)).scalar_one()
            fix_task = db.execute(
                select(Task).where(Task.org_id == org_id, Task.parent_task_id == task.id).order_by(Task.created_at.desc())
            ).scalar_one_or_none()
            return task, fix_task
        raise

    return task, fix_task
