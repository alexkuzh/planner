from uuid import UUID

from fastapi import Header, HTTPException


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

