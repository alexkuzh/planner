# app/services/task_transition_service.py
from __future__ import annotations

import json
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any
from enum import Enum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert


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
    """
    Canonicalize payload for idempotency compare.

    ВАЖНО: игнорируем серверные поля, которые сервис сам добавляет в payload
    (например fix_task_id), иначе повтор одного и того же запроса будет
    считаться "другим" и падать IdempotencyConflict.
    """
    data = dict(obj or {})
    data.pop("fix_task_id", None)  # server-generated
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def _same_request(
    existing: TaskTransition,
    *,
    task_id: UUID,
    actor_user_id: UUID,
    action: str,
    expected_row_version: int,
    payload: dict[str, Any],
) -> bool:
    # NOTE: для idempotency сравниваем НОРМАЛИЗОВАННЫЕ payload,
    # чтобы UUID/Enum/пробелы не давали ложный конфликт.
    existing_payload_norm = _normalize_payload_for_idempotency(action, existing.payload or {})
    incoming_payload_norm = _normalize_payload_for_idempotency(action, payload or {})

    return (
        existing.task_id == task_id
        and existing.actor_user_id == actor_user_id
        and existing.action == action
        and existing.expected_row_version == expected_row_version
        and _canon(existing_payload_norm) == _canon(incoming_payload_norm)
    )

def _to_uuid_str(value: Any) -> Any:
    """
    Нормализация UUID-полей:
    - UUID(...) -> "xxxxxxxx-xxxx-..."
    - "uuid-string" -> "uuid-string" (в каноническом виде)
    - остальное -> как есть
    """
    if value is None:
        return None
    try:
        return str(UUID(str(value)))
    except Exception:
        return value


def _normalize_payload_for_idempotency(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Нормализация payload для сравнения idempotency.

    Важно:
    - Делает "семантическую эквивалентность" для UUID / Enum / строк.
    - Не выкидывает неизвестные ключи (т.е. extra keys всё ещё будут конфликтом).
      Это сохраняет строгий контракт: "тот же client_event_id => тот же запрос".
    """
    p = dict(payload or {})

    # --- common UUID-ish normalization ---
    # assign_to/user_id часто бывают UUID или str(UUID) — приводим к str(UUID)
    if "assign_to" in p:
        p["assign_to"] = _to_uuid_str(p.get("assign_to"))
    if "user_id" in p:
        p["user_id"] = _to_uuid_str(p.get("user_id"))

    # --- reject semantics ---
    if action == "reject":
        # reason/fix_title сравниваем без "шумовых" пробелов по краям
        if "reason" in p and p["reason"] is not None:
            p["reason"] = str(p["reason"]).strip()
        if "fix_title" in p and p["fix_title"] is not None:
            p["fix_title"] = str(p["fix_title"]).strip()

        # severity может прийти как Enum или как строка
        sev = p.get("severity", None)
        if isinstance(sev, Enum):
            p["severity"] = str(sev.value)
        elif sev is not None:
            p["severity"] = str(sev)

    return p

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

    # NOTE: нормализуем payload для:
    # 1) строгого idempotency-сравнения по смыслу
    # 2) стабильного хранения payload в task_transitions
    payload_norm = _normalize_payload_for_idempotency(action, payload)

    # 0) Idempotency (strict)
    if client_event_id is not None:
        existing = db.execute(
            select(TaskTransition).where(
                TaskTransition.org_id == org_id,
                TaskTransition.client_event_id == client_event_id,
            )
        ).scalar_one_or_none()

        if existing is not None:
            if not _same_request(
                    existing,
                    task_id=task_id,
                    actor_user_id=actor_user_id,
                    action=action,
                    expected_row_version=expected_row_version,
                    payload=payload_norm,
            ):
                raise IdempotencyConflict("client_event_id already used with different request data")

            return _load_result_by_transition(db, existing)

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


    # 3) FSM (но Task пока НЕ меняем)
    to_status, side_effects = apply_transition(from_status, action, payload=payload)

    # 4) Prepare payload for transition (включая fix_task_id, если появится)
    tr_payload = dict(payload_norm)
    fix_task: Task | None = None

    # 5) Side effects (reject => create fix-task) — может добавить fix_task_id в payload
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

            tr_payload["fix_task_id"] = str(fix_task.id)

    # 6) Write transition first (race-safe). result_row_version считаем заранее.
    values = {
        "id": uuid4(),
        "org_id": org_id,
        "project_id": task.project_id,
        "task_id": task.id,
        "actor_user_id": actor_user_id,
        "action": action,
        "from_status": from_status.value,
        "to_status": to_status.value,
        "payload": tr_payload,
        "client_event_id": client_event_id,
        "created_at": _now(),
        "expected_row_version": expected_row_version,
        "result_row_version": expected_row_version + 1,
    }

    stmt = pg_insert(TaskTransition).values(**values)

    if client_event_id is not None:
        stmt = (
            stmt.on_conflict_do_nothing(
                index_elements=[TaskTransition.org_id, TaskTransition.client_event_id],
                index_where=TaskTransition.client_event_id.is_not(None),
            )
            .returning(TaskTransition.id)
        )
        inserted_id = db.execute(stmt).scalar_one_or_none()

        # гонка/повтор: transition не вставился => возвращаем existing и НЕ трогаем Task
        if inserted_id is None:
            existing = db.execute(
                select(TaskTransition).where(
                    TaskTransition.org_id == org_id,
                    TaskTransition.client_event_id == client_event_id,
                )
            ).scalar_one()
            return _load_result_by_transition(db, existing)
    else:
        db.execute(stmt)

    # 7) ТОЛЬКО если transition реально вставился — применяем изменения к Task
    if action == "assign":
        assign_to = payload.get("assign_to") or payload.get("user_id")
        if not assign_to:
            raise TransitionNotAllowed("Action 'assign' требует payload.assign_to (user_id).")
        task.assigned_to = UUID(str(assign_to))
        task.assigned_at = _now()
    elif action == "unassign":
        task.assigned_to = None
        task.assigned_at = None

    task.status = to_status.value
    task.updated_at = _now()
    task.row_version = expected_row_version + 1

    db.flush()
    return task, fix_task
