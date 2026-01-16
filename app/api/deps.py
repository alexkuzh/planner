# app/api/deps.py
from __future__ import annotations

from uuid import UUID

from fastapi import Header, HTTPException, status


def get_current_user_id(
        x_actor_user_id: str | None = Header(
            default=None,
            alias="X-Actor-User-Id",
            description="UUID пользователя, выполняющего действие. Временная auth для MVP.",
            examples=["33333333-3333-3333-3333-333333333333"],
        ),
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


# TODO(auth): убрать default role после внедрения auth middleware
def get_actor_role(
        x_role: str = Header(
            "system",
            alias="X-Role",
            description=(
                    "RBAC роль пользователя. "
                    "MVP default = system. "
                    "В production будет извлекаться из auth context."
            ),
            examples=["system", "lead", "executor"],
        )
) -> str:
    """
    Извлекает роль пользователя из заголовка X-Role.

    MVP: дефолт = 'system' для удобства тестирования.
    Production: будет извлекаться из JWT/session после внедрения auth middleware.
    """
    return x_role.strip()


def get_actor_role_optional(
        x_role: str | None = Header(
            default=None,
            alias="X-Role",
            description="RBAC роль пользователя (опционально для публичных endpoint).",
            examples=["system", "lead", "executor"],
        )
) -> str | None:
    """
    For public/read-only endpoints: role may be omitted.
    """
    if not x_role or not x_role.strip():
        return None
    return x_role.strip()