# app/api/deps.py
from __future__ import annotations

from uuid import UUID

from fastapi import Header, HTTPException, status


def get_current_user_id(
    x_actor_user_id: str | None = Header(default=None, alias="X-Actor-User-Id"),
) -> UUID:
    """
    Временная авторизация для MVP:
    пользователь передаёт X-Actor-User-Id: <uuid>
    """
    if not x_actor_user_id:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Actor-User-Id header",
        )

    try:
        return UUID(x_actor_user_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid X-Actor-User-Id format (must be UUID)",
        )


def get_actor_role(x_role: str | None = Header(default=None, alias="X-Role")) -> str:
    if not x_role or not x_role.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Role header",
        )
    return x_role.strip()


def get_actor_role_optional(x_role: str | None = Header(default=None, alias="X-Role")) -> str | None:
    """
    For public/read-only endpoints: role may be omitted.
    """
    if not x_role or not x_role.strip():
        return None
    return x_role.strip()