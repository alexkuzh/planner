from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.qc_inspection import QcResult


class QcDecisionRequest(BaseModel):
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
    inspector_user_id: UUID = Field(
        ...,
        description="QC инспектор, принимающий решение.",
        examples=["44444444-4444-4444-4444-444444444444"],
    )

    result: QcResult = Field(
        ...,
        description="Результат QC: approved / rejected.",
        examples=["approved", "rejected"],
    )

    notes: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "Комментарий/причина решения QC. "
            "Обязательно, если result='rejected' (см. валидацию)."
        ),
        examples=["Все в порядке", "Найдены дефекты: перекос/царапины, требуется исправление"],
    )

    @model_validator(mode="after")
    def _reject_requires_notes(self):
        if self.result == QcResult.rejected and (self.notes is None or not self.notes.strip()):
            raise ValueError("notes is required when result='rejected'")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "22222222-2222-2222-2222-222222222222",
                    "inspector_user_id": "44444444-4444-4444-4444-444444444444",
                    "result": "approved",
                    "notes": "Ок",
                },
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "22222222-2222-2222-2222-222222222222",
                    "inspector_user_id": "44444444-4444-4444-4444-444444444444",
                    "result": "rejected",
                    "notes": "Найдены дефекты: требуется исправление",
                },
            ]
        }
    }


class QcInspectionRead(BaseModel):
    id: UUID
    org_id: UUID
    project_id: UUID
    deliverable_id: UUID

    inspector_user_id: UUID
    responsible_user_id: UUID | None = None

    result: QcResult
    notes: str | None = None

    created_at: datetime

    model_config = {"from_attributes": True}
