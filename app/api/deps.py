# app/api/deps.py
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException


# -----------------------------------------------------------------------------
# MVP auth headers
# -----------------------------------------------------------------------------


def get_current_user_id(
    x_actor_user_id: str | None = Header(
        default=None,
        alias="X-Actor-User-Id",
        description="UUID пользователя, выполняющего действие. Временная auth для MVP.",
        examples=["33333333-3333-3333-3333-333333333333"],
    ),
) -> UUID:
    """MVP auth: X-Actor-User-Id header."""
    if not x_actor_user_id:
        raise HTTPException(status_code=401, detail="Missing X-Actor-User-Id header")
    try:
        return UUID(x_actor_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid X-Actor-User-Id format (must be UUID)") from e


# Backward-compatible alias
def get_actor_user_id(actor_user_id: UUID = Depends(get_current_user_id)) -> UUID:
    return actor_user_id


def get_actor_role(
    x_role: str = Header(
        "system",
        alias="X-Role",
        description=(
            "RBAC роль пользователя. "
            "MVP default = system. "
            "В production будет извлекаться из auth context."
        ),
        examples=["system", "lead", "executor", "supervisor"],
    )
) -> str:
    """MVP role header. Default system for convenience."""
    return x_role.strip()


def get_actor_role_optional(
    x_role: str | None = Header(
        default=None,
        alias="X-Role",
        description="RBAC роль пользователя (опционально для публичных endpoint).",
        examples=["system", "lead", "executor", "supervisor"],
    )
) -> str | None:
    if not x_role or not x_role.strip():
        return None
    return x_role.strip()


def get_org_id(
    x_org_id: str | None = Header(
        default=None,
        alias="X-Org-Id",
        description="Organization context (required for protected write endpoints)",
        examples=["11111111-1111-1111-1111-111111111111"],
        include_in_schema=True,
    ),
) -> UUID:
    """B1 Auth Hardening: org context comes from X-Org-Id header."""
    if not x_org_id:
        raise HTTPException(status_code=401, detail="Missing X-Org-Id header")
    try:
        return UUID(x_org_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid X-Org-Id format (must be UUID)") from e


@dataclass(frozen=True)
class ActorContext:
    org_id: UUID
    actor_user_id: UUID
    role: str


def get_actor_context(
    org_id: UUID = Depends(get_org_id),
    actor_user_id: UUID = Depends(get_actor_user_id),
    role: str = Depends(get_actor_role),
) -> ActorContext:
    return ActorContext(org_id=org_id, actor_user_id=actor_user_id, role=role)
