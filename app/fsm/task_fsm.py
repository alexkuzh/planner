# app/fsm/task_fsm.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.models.task import TaskStatus

"""Task FSM: производственный цикл задачи.

Финальная модель (без planned/in_review/rejected):
  blocked -> available -> assigned -> in_progress -> submitted -> done
  cancel -> canceled

ВАЖНО:
- QC НЕ управляет состояниями Task напрямую.
- QC работает через qc_inspections / deliverable QC flow.
- Поэтому в Task FSM НЕ должно быть действий вида qc_*.
"""


class TransitionNotAllowed(Exception):
    pass


class Action(str, Enum):
    # pool readiness
    UNBLOCK = "unblock"  # blocked -> available

    # assignment
    SELF_ASSIGN = "self_assign"  # available -> assigned
    ASSIGN = "assign"  # available -> assigned (lead/supervisor)

    # execution
    START = "start"  # assigned -> in_progress
    SUBMIT = "submit"  # in_progress -> submitted

    # review
    REVIEW_APPROVE = "review_approve"  # submitted -> done
    REVIEW_REJECT = "review_reject"  # submitted -> in_progress (+ optional fix-task)

    # controlled return to pool
    SHIFT_RELEASE = "shift_release"  # assigned/in_progress -> available
    RECALL_TO_POOL = "recall_to_pool"  # assigned/in_progress -> available

    # flag / signal (no status change)
    ESCALATE = "escalate"

    # terminal
    CANCEL = "cancel"


@dataclass(frozen=True)
class SideEffect:
    """Declarative side effects for the service layer to execute."""

    kind: str
    payload: dict[str, Any]


NON_TERMINAL = {
    TaskStatus.blocked,
    TaskStatus.available,
    TaskStatus.assigned,
    TaskStatus.in_progress,
    TaskStatus.submitted,
}

TERMINAL = {
    TaskStatus.done,
    TaskStatus.canceled,
}


# action -> allowed from statuses + to status
TRANSITIONS: dict[Action, tuple[set[TaskStatus], TaskStatus]] = {
    Action.UNBLOCK: ({TaskStatus.blocked}, TaskStatus.available),

    Action.SELF_ASSIGN: ({TaskStatus.available}, TaskStatus.assigned),
    Action.ASSIGN: ({TaskStatus.available}, TaskStatus.assigned),

    Action.START: ({TaskStatus.assigned}, TaskStatus.in_progress),
    Action.SUBMIT: ({TaskStatus.in_progress}, TaskStatus.submitted),

    Action.REVIEW_APPROVE: ({TaskStatus.submitted}, TaskStatus.done),
    Action.REVIEW_REJECT: ({TaskStatus.submitted}, TaskStatus.in_progress),

    Action.SHIFT_RELEASE: ({TaskStatus.assigned, TaskStatus.in_progress}, TaskStatus.available),
    Action.RECALL_TO_POOL: ({TaskStatus.assigned, TaskStatus.in_progress}, TaskStatus.available),

    Action.CANCEL: (NON_TERMINAL, TaskStatus.canceled),
}


def apply_transition(
    current: TaskStatus,
    action_raw: str,
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[TaskStatus, list[SideEffect]]:
    """Returns (new_status, side_effects).

    Side effects are executed by the service layer in the same DB transaction.
    """

    payload = payload or {}
    action_raw = action_raw.strip()

    try:
        action = Action(action_raw)
    except ValueError:
        allowed = ", ".join(a.value for a in Action)
        raise TransitionNotAllowed(f"Unknown action: '{action_raw}'. Allowed actions: {allowed}")

    # ESCALATE does not change status, but can produce a side-effect.
    if action is Action.ESCALATE:
        if current in TERMINAL:
            raise TransitionNotAllowed("Action 'escalate' not allowed from terminal status")
        return current, [SideEffect(kind="escalate", payload={"message": (payload.get("message") or "").strip()})]

    allowed_from, to_status = TRANSITIONS[action]
    if current not in allowed_from:
        allowed_from_str = ", ".join(sorted(s.value for s in allowed_from))
        raise TransitionNotAllowed(
            f"Action '{action.value}' not allowed from status '{current.value}'. "
            f"Allowed from: {allowed_from_str}."
        )

    side_effects: list[SideEffect] = []

    # REVIEW_REJECT may optionally create a fix-task (policy-level). We keep the payload shape
    # compatible with the previous implementation.
    if action is Action.REVIEW_REJECT:
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
