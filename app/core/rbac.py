from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Forbidden(Exception):
    """
    Service-level RBAC exception.
    API layer maps this to HTTP 403 deterministically.
    """
    detail: str


# Source of truth: current API actions (schemas/transition.py) + FSM Action enum.
# If an action is missing here -> it MUST be forbidden (403) deterministically.
ALLOW: dict[str, set[str]] = {
    # Pool / operational
    "task.unblock": {"system", "lead"},
    "task.self_assign": {"executor", "lead"},
    "task.assign": {"lead", "supervisor"},
    "task.unassign": {"lead", "supervisor"},
    "task.start": {"executor", "lead"},
    "task.submit": {"executor", "lead"},

    # Review-ish (if present as task transitions)
    "task.review_approve": {"lead", "supervisor"},
    "task.review_reject": {"lead", "supervisor"},

    # Pool management
    "task.shift_release": {"lead", "supervisor"},
    "task.recall_to_pool": {"lead", "supervisor"},
    "task.escalate": {"executor", "lead", "supervisor"},

    # Misc
    "task.cancel": {"lead", "supervisor"},

    # Deliverables (consumer-facing workflow actions)
    # NOTE: these permissions are enforced at API layer for deterministic 403 (B5).
    "deliverable.bootstrap": {"system", "lead"},
    "deliverable.signoff": {"system", "lead", "supervisor"},
    "deliverable.submit_to_qc": {"system", "lead", "supervisor"},
    "deliverable.qc_decision": {"system", "lead", "supervisor"},
}


def ensure_allowed(permission: str, actor_role: str) -> None:
    allowed_roles = ALLOW.get(permission)
    if not allowed_roles or actor_role not in allowed_roles:
        raise Forbidden(
            f"Forbidden: role '{actor_role}' is not allowed for '{permission}'"
        )


def is_allowed(permission: str, actor_role: str) -> bool:
    roles = ALLOW.get(permission)
    return bool(roles) and actor_role in roles


def list_allowed_permissions_for_role(role: str) -> list[str]:
    return sorted([perm for perm, roles in ALLOW.items() if role in roles])
