# app/schemas/deliverable.py

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.deliverable import DeliverableStatus


class DeliverableCreate(BaseModel):
    project_id: UUID = Field(
        ...,
        description="Проект. Пока передаём явно, позже будет из auth/context.",
        examples=["22222222-2222-2222-2222-222222222222"],
    )

    deliverable_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Тип изделия в рамках проекта (внутри проекта один тип deliverable).",
        examples=["box_v1"],
    )
    serial: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Серийный номер приходит извне. Уникален в рамках (org_id).",
        examples=["SN-2026-0001"],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "project_id": "22222222-2222-2222-2222-222222222222",
                    "deliverable_type": "box_v1",
                    "serial": "SN-2026-0001",
                }
            ]
        }
    }


class DeliverableRead(BaseModel):
    id: UUID
    org_id: UUID
    project_id: UUID

    deliverable_type: str
    serial: str
    status: DeliverableStatus

    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
