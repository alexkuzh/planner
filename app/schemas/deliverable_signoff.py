# app/schemas/deliverable_signoff.py

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.deliverable_signoff import SignoffResult


class DeliverableSignoffCreate(BaseModel):
    org_id: UUID = Field(
        ...,
        description="Организация (мультитенантность). Пока передаём явно, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    )
    project_id: UUID = Field(
        ...,
        description="Проект. Пока передаём явно, позже будет из auth/context.",
        examples=["22222222-2222-2222-2222-222222222222"],
    )
    signed_off_by: UUID = Field(
        ...,
        description="Кто подписывает (точка ответственности).",
        examples=["33333333-3333-3333-3333-333333333333"],
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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "22222222-2222-2222-2222-222222222222",
                    "signed_off_by": "33333333-3333-3333-3333-333333333333",
                    "result": "approved",
                    "comment": "Все задачи выполнены",
                },
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "22222222-2222-2222-2222-222222222222",
                    "signed_off_by": "33333333-3333-3333-3333-333333333333",
                    "result": "rejected",
                    "comment": "Найдены дефекты, требуется доработка",
                },
            ]
        }
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
