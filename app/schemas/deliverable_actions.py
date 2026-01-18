#  app/schemas/deliverable_actions.py

from __future__ import annotations

from uuid import UUID
from pydantic import BaseModel, Field


class SubmitToQcRequest(BaseModel):
    project_id: UUID = Field(
        ...,
        description="Проект. Пока передаём явно, позже будет из auth/context.",
        examples=["22222222-2222-2222-2222-222222222222"],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "project_id": "22222222-2222-2222-2222-222222222222",
                }
            ]
        },
    }


class DeliverableBootstrapRequest(BaseModel):
    project_id: UUID = Field(
        ...,
        description="Проект. Пока передаём явно, позже будет из auth/context.",
        examples=["22222222-2222-2222-2222-222222222222"],
    )
    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "project_id": "22222222-2222-2222-2222-222222222222",
                }
            ]
        },
    }