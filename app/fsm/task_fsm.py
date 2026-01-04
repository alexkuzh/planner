from __future__ import annotations

from app.models.task import TaskStatus


class TransitionNotAllowed(Exception):
    pass


# action -> (from_status, to_status)
TRANSITIONS: dict[str, tuple[TaskStatus, TaskStatus]] = {
    "start": (TaskStatus.new, TaskStatus.in_progress),
    "finish": (TaskStatus.in_progress, TaskStatus.done),
    "reopen": (TaskStatus.done, TaskStatus.in_progress),
}


def apply_transition(current: TaskStatus, action: str) -> TaskStatus:
    """
    Apply a transition action to the current TaskStatus and return the new status.

    Rules:
      - action must exist in TRANSITIONS
      - current status must match the expected 'from' status for that action
    """
    action = action.strip()

    if action not in TRANSITIONS:
        allowed = ", ".join(sorted(TRANSITIONS.keys()))
        raise TransitionNotAllowed(f"Unknown action: '{action}'. Allowed actions: {allowed}")

    expected_from, to_status = TRANSITIONS[action]
    if current != expected_from:
        raise TransitionNotAllowed(
            f"Action '{action}' not allowed from status '{current.value}'. "
            f"Expected '{expected_from.value}'."
        )
    return to_status
