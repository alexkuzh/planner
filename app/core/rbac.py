# app/core/rbac.py
from __future__ import annotations

from typing import Mapping, Set


class Forbidden(Exception):
    """Raise when actor role is not allowed for an operation."""
    pass


# MVP roles (stringly-typed on purpose; later replace with Enum/JWT claims)
# Keep permissions stable even if role names evolve.
ALLOW: Mapping[str, Set[str]] = {
    # ---- Deliverables ----
    "deliverable.create": {"project_creator", "receiver"},
    "deliverable.bootstrap": {"system"},
    "deliverable.submit_to_qc": {"internal_controller"},
    "deliverable.qc_decision": {"qc"},
    "deliverable.signoff": {"lead", "responsible"},

    # ---- Tasks (FSM transitions) ----
    "task.plan": {"system", "lead"},
    "task.assign": {"lead", "supervisor"},
    "task.unassign": {"lead", "supervisor"},
    "task.start": {"executor", "lead"},
    "task.submit": {"executor", "lead"},
    "task.approve": {"lead", "supervisor"},
    "task.reject": {"lead", "supervisor"},

    # ---- Fix tasks ----
    "fix.worker_initiative": {"qualified_worker", "executor", "lead", "supervisor"},
    "fix.qc_reject": {"qc"},
}


def ensure_allowed(permission: str, role: str) -> None:
    allowed = ALLOW.get(permission, set())
    if role not in allowed:
        raise Forbidden(f"Role '{role}' is not allowed for '{permission}'")
