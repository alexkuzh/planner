# app/services/task_transition_service.py
from __future__ import annotations

import json
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.task import Task, TaskStatus, FixSeverity, FixSource
from app.models.task_transition import TaskTransition
from app.fsm.task_fsm import apply_transition, TransitionNotAllowed
from app.services.task_fix_service import TaskFixService

FIX_EFFECT_CREATE = "create_fix_task"


class VersionConflict(Exception):
    pass


class IdempotencyConflict(Exception):
    """client_event_id reused with different request data."""
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_severity(value) -> FixSeverity:
    if value is None:
        return FixSeverity.major
    if isinstance(value, FixSeverity):
        return value
    try:
        return FixSeverity(str(value))
    except Exception:
        return FixSeverity.major


def _canon(obj) -> str:
    return json.dumps(obj or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _same_request(
    existing: TaskTransition,
    *,
    task_id: UUID,
    actor_user_id: UUID,
    action: str,
    expected_row_version: int,
    payload: dict[str, Any],
) -> bool:
    return (
        existing.task_id == task_id
        and existing.actor_user_id == actor_user_id
        and existing.action == action
        and (existing.expected_row_version or None) == expected_row_version
        and _canon_payload(existing.payload) == _canon_payload(payload)
    )


def _load_result_by_transition(db: Session, tr: TaskTransition) -> tuple[Task, Task | None]:
    task = db.execute(
        select(Task).where(Task.org_id == tr.org_id, Task.id == tr.task_id)
    ).scalar_one()

    fix_task = None
    if tr.payload and isinstance(tr.payload, dict) and "fix_task_id" in tr.payload:
        fix_task = db.get(Task, UUID(str(tr.payload["fix_task_id"])))

    return task, fix_task



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
    payload = payload or {}

    # 0) Idempotency (strict)
    if client_event_id is not None:
        existing = db.execute(
            select(TaskTransition).where(
                TaskTransition.org_id == org_id,
                TaskTransition.client_event_id == client_event_id,
            )
        ).scalar_one_or_none()

        if existing is not None:
            same = (
                existing.task_id == task_id
                and existing.actor_user_id == actor_user_id
                and existing.action == action
                and (existing.expected_row_version or 0) == expected_row_version
                and _canon(existing.payload) == _canon(payload)
            )
            if not same:
                raise IdempotencyConflict("client_event_id already used with different request data")

            task = db.execute(
                select(Task).where(Task.org_id == org_id, Task.id == existing.task_id)
            ).scalar_one()

            fix_task = None
            if existing.payload and "fix_task_id" in existing.payload:
                fix_task = db.get(Task, UUID(existing.payload["fix_task_id"]))

            return task, fix_task

    # 1) Load task row (NO FOR UPDATE: rely on row_version)
    task: Task | None = db.execute(
        select(Task).where(Task.org_id == org_id, Task.id == task_id)
    ).scalar_one_or_none()

    if task is None:
        raise KeyError("Task not found")

    # 2) Optimistic lock
    if task.row_version != expected_row_version:
        raise VersionConflict(f"Expected row_version={expected_row_version}, actual={task.row_version}")

    from_status = TaskStatus(task.status) if isinstance(task.status, str) else task.status

    # 3) FSM
    to_status, side_effects = apply_transition(from_status, action, payload=payload)

    # 3.1) Action-specific fields
    if action == "assign":
        assign_to = payload.get("assign_to") or payload.get("user_id")
        if not assign_to:
            raise TransitionNotAllowed("Action 'assign' требует payload.assign_to (user_id).")
        task.assigned_to = UUID(str(assign_to))
        task.assigned_at = _now()

    elif action == "unassign":
        task.assigned_to = None
        task.assigned_at = None

    # 4) Update task
    task.status = to_status.value
    task.updated_at = _now()
    task.row_version += 1

    # 5) Write transition (ORM объект)
    tr = TaskTransition(
        id=uuid4(),
        org_id=org_id,
        project_id=task.project_id,
        task_id=task.id,
        actor_user_id=actor_user_id,
        action=action,
        from_status=from_status.value,
        to_status=to_status.value,
        payload=dict(payload),
        client_event_id=client_event_id,
        created_at=_now(),
        expected_row_version=expected_row_version,
        result_row_version=task.row_version,
    )
    db.add(tr)

    fix_task: Task | None = None

    # 6) Side effects (могут дописать tr.payload)
    for eff in side_effects:
        if eff.kind == FIX_EFFECT_CREATE:
            reason = (eff.payload.get("reason") or "").strip()
            fix_title = (eff.payload.get("fix_title") or "").strip()
            severity = _parse_severity(eff.payload.get("severity"))

            if task.deliverable_id is None:
                raise TransitionNotAllowed("Cannot create fix-task: task is not linked to deliverable_id")

            svc = TaskFixService(db)
            fix_task = svc.create_fix(
                org_id=task.org_id,
                project_id=task.project_id,
                deliverable_id=task.deliverable_id,
                actor_user_id=actor_user_id,
                title=fix_title or f"Fix: {task.title}",
                description=reason or None,
                source=FixSource.supervisor_request,
                severity=severity,
                minutes_spent=None,
                origin_task_id=task.id,
                qc_inspection_id=None,
                attachments=None,
            )

            tr.payload["fix_task_id"] = str(fix_task.id)

    # 7) Flush один раз. Для гонки используем savepoint (nested tx)
    nested = db.begin_nested()
    try:
        db.flush()
        nested.commit()
    except IntegrityError:
        # IMPORTANT: откатываем savepoint, НЕ внешний transaction фикстуры
        nested.rollback()

        # unique(org_id, client_event_id) => конкурентная вставка / retry
        if client_event_id is not None:
            existing = db.execute(
                select(TaskTransition).where(
                    TaskTransition.org_id == org_id,
                    TaskTransition.client_event_id == client_event_id,
                )
            ).scalar_one()

            task = db.execute(
                select(Task).where(Task.org_id == org_id, Task.id == existing.task_id)
            ).scalar_one()

            fix_task = None
            if existing.payload and "fix_task_id" in existing.payload:
                fix_task = db.get(Task, UUID(existing.payload["fix_task_id"]))

            return task, fix_task

        raise

    return task, fix_task

