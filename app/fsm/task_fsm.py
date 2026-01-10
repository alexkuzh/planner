# app/fsm/task_fsm.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.models.task import TaskStatus


class TransitionNotAllowed(Exception):
    pass


class Action(str, Enum):
    PLAN = "plan"
    ASSIGN = "assign"
    UNASSIGN = "unassign"
    START = "start"
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"


@dataclass(frozen=True)
class SideEffect:
    """Declarative side effects for the service layer to execute."""
    kind: str
    payload: dict[str, Any]


# Какие статусы считаем "не финальными"
NON_TERMINAL = {
    TaskStatus.new,
    TaskStatus.planned,
    TaskStatus.assigned,
    TaskStatus.in_progress,
    TaskStatus.in_review,
}

TERMINAL = {
    TaskStatus.done,
    TaskStatus.rejected,
    TaskStatus.canceled,
}


# action -> allowed from statuses + to status
# Важно: start только из assigned (а не из new)
TRANSITIONS: dict[Action, tuple[set[TaskStatus], TaskStatus]] = {
    Action.PLAN: ({TaskStatus.new}, TaskStatus.planned),
    Action.ASSIGN: ({TaskStatus.new, TaskStatus.planned}, TaskStatus.assigned),
    Action.UNASSIGN: ({TaskStatus.assigned}, TaskStatus.planned),

    Action.START: ({TaskStatus.assigned}, TaskStatus.in_progress),
    Action.SUBMIT: ({TaskStatus.in_progress}, TaskStatus.in_review),

    Action.APPROVE: ({TaskStatus.in_review}, TaskStatus.done),
    Action.REJECT: ({TaskStatus.in_review}, TaskStatus.rejected),

    Action.CANCEL: (NON_TERMINAL, TaskStatus.canceled),
}


def apply_transition(
    current: TaskStatus,
    action_raw: str,
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[TaskStatus, list[SideEffect]]:
    """
    Returns (new_status, side_effects).
    Side effects are executed by the service layer in the same DB transaction.
    """
    payload = payload or {}
    action_raw = action_raw.strip()

    try:
        action = Action(action_raw)
    except ValueError:
        allowed = ", ".join(a.value for a in Action)
        raise TransitionNotAllowed(f"Unknown action: '{action_raw}'. Allowed actions: {allowed}")

    allowed_from, to_status = TRANSITIONS[action]
    if current not in allowed_from:
        allowed_from_str = ", ".join(sorted(s.value for s in allowed_from))
        raise TransitionNotAllowed(
            f"Action '{action.value}' not allowed from status '{current.value}'. "
            f"Allowed from: {allowed_from_str}."
        )

    side_effects: list[SideEffect] = []

    # Reject => create fix-task (в MVP — всегда, чтобы не было "сломал данные")
    if action is Action.REJECT:
        reason = (payload.get("reason") or "").strip()
        fix_title = (payload.get("fix_title") or "").strip()
        assign_to = payload.get("assign_to")  # optional user_id

        side_effects.append(
            SideEffect(
                kind="create_fix_task",
                payload={
                    "reason": reason,
                    "fix_title": fix_title,
                    "assign_to": assign_to,
                },
            )
        )

    return to_status, side_effects
