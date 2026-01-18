# app/schemas/deliverable_signoff.py

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.deliverable_signoff import SignoffResult


class DeliverableSignoffCreate(BaseModel):
    project_id: UUID = Field(
        ...,
        description="Проект. Пока передаём явно, позже будет из auth/context.",
        examples=["22222222-2222-2222-2222-222222222222"],
    )

    result: SignoffResult = Field(
        default=SignoffResult.approved,
        description="Результат production sign-off: approved / rejected.",
        examples=["approved", "rejected"],
    )

    comment: str | None = Field(
        default=None,
        max_length=1000,
        description="Комментарий (опционально). Для rejected желательно указать причину.",
        examples=["Ок", "Не соответствует чертежу, требуется исправление"],
    )

    # B2: headers-first only; forbid legacy fields in body
    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "project_id": "22222222-2222-2222-2222-222222222222",
                    "result": "approved",
                    "comment": "Все задачи выполнены",
                },
                {
                    "project_id": "22222222-2222-2222-2222-222222222222",
                    "result": "rejected",
                    "comment": "Найдены дефекты, требуется доработка",
                },
            ]
        },
    }


class DeliverableSignoffRead(BaseModel):
    id: UUID
    org_id: UUID
    project_id: UUID
    deliverable_id: UUID

    signed_off_by: UUID
    result: SignoffResult
    comment: str | None = None

    created_at: datetime

    model_config = {"from_attributes": True}
