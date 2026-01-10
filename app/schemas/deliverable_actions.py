#  app/schemas/deliverable_actions.py

from __future__ import annotations

from uuid import UUID
from pydantic import BaseModel, Field


class SubmitToQcRequest(BaseModel):
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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "22222222-2222-2222-2222-222222222222",
                }
            ]
        }
    }


class DeliverableBootstrapRequest(BaseModel):
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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "22222222-2222-2222-2222-222222222222",
                }
            ]
        }
    }