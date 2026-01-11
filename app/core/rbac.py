# app/core/rbac.py
from __future__ import annotations

from typing import Mapping, Set


class Forbidden(Exception):
    """Raised when actor role is not allowed for an operation."""
    pass


def _aliases(prefix: str, actions: Set[str]) -> Set[str]:
    """
    Build permission-key aliases for the same logical action.

    In the codebase we may generate permissions in different formats, e.g.:
      - "task.plan"
      - "task.TaskAction.plan"

    To avoid RBAC drift during MVP, we whitelist both formats.
    """
    out: Set[str] = set()
    for a in actions:
        out.add(f"{prefix}.{a}")
        out.add(f"{prefix}.TaskAction.{a}")
    return out


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
    # Note: accept both "task.<action>" and "task.TaskAction.<action>" to match
    # whatever permission-key format a caller uses.
    **{k: {"system", "lead"} for k in _aliases("task", {"plan"})},
    **{k: {"lead", "supervisor"} for k in _aliases("task", {"assign", "unassign", "approve", "reject"})},
    **{k: {"executor", "lead"} for k in _aliases("task", {"start", "submit"})},

    # ---- Fix tasks ----
    "fix.worker_initiative": {"qualified_worker", "executor", "lead", "supervisor"},
    "fix.qc_reject": {"qc"},
}


def ensure_allowed(permission: str, role: str) -> None:
    allowed = ALLOW.get(permission, set())
    if role not in allowed:
        raise Forbidden(f"Role '{role}' is not allowed for '{permission}'")