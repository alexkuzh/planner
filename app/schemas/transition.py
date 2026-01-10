# app/schemas/transition.py
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TaskAction(str, enum.Enum):
    plan = "plan"
    assign = "assign"
    unassign = "unassign"
    start = "start"
    submit = "submit"
    approve = "approve"
    reject = "reject"


class TaskTransitionRequest(BaseModel):
    org_id: UUID = Field(
        ...,
        examples=["11111111-1111-1111-1111-111111111111"],
        description="Организация (мультитенантность). Пока передаём явно, позже будет из auth.",
    )
    actor_user_id: UUID = Field(
        ...,
        examples=["33333333-3333-3333-3333-333333333333"],
        description="Кто выполняет действие. Пока передаём явно, позже будет из auth.",
    )

    action: TaskAction = Field(
        ...,
        examples=["plan", "assign", "start", "submit", "approve", "reject"],
        description="Действие FSM.",
    )

    expected_row_version: int = Field(
        ...,
        ge=1,
        examples=[1],
        description="Optimistic lock: ожидаемая версия строки задачи.",
    )

    client_event_id: Optional[UUID] = Field(
        default=None,
        examples=["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
        description="Идемпотентность. Можно не передавать. Если передаёшь — новый UUID на каждый запрос.",
    )

    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Данные, специфичные для действия (например assign_to или reason).",
        examples=[
            {},  # plan/start/submit/approve
            {"assign_to": "33333333-3333-3333-3333-333333333333"},  # assign
            {
                "reason": "Найдены дефекты, требуется доработка",
                "fix_title": "Исправить дефекты по задаче",
                "assign_to": "33333333-3333-3333-3333-333333333333",
            },  # reject -> fix-task
        ],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "actor_user_id": "33333333-3333-3333-3333-333333333333",
                    "action": "assign",
                    "expected_row_version": 2,
                    "client_event_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "payload": {"assign_to": "33333333-3333-3333-3333-333333333333"},
                },
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "actor_user_id": "33333333-3333-3333-3333-333333333333",
                    "action": "reject",
                    "expected_row_version": 5,
                    "client_event_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    "payload": {
                        "reason": "Найдены дефекты, требуется доработка",
                        "fix_title": "Исправить дефекты по задаче",
                        "assign_to": "33333333-3333-3333-3333-333333333333",
                    },
                },
            ]
        }
    }


class TaskTransitionResponse(BaseModel):
    task_id: UUID
    status: str
    row_version: int
    fix_task_id: Optional[UUID] = None


class TaskTransitionItem(BaseModel):
    id: UUID
    task_id: UUID
    action: TaskAction
    from_status: str
    to_status: str
    payload: dict[str, Any]
    actor_user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
