#  app/schemas/deliverable_actions.py

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


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

    actor_user_id: UUID = Field(
        ...,
        description="Пользователь, инициирующий submit_to_qc (audit / ownership).",
        examples=["33333333-3333-3333-3333-333333333333"],
    )

    # A1 (API Hardening): forbid unknown fields in request bodies.
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "22222222-2222-2222-2222-222222222222",
                    "actor_user_id": "33333333-3333-3333-3333-333333333333",
                }
            ]
        },
    )


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
    actor_user_id: UUID = Field(
        ...,
        description="Пользователь, инициирующий bootstrap (audit / ownership).",
        examples=["33333333-3333-3333-3333-333333333333"],
    )

    # A1 (API Hardening): forbid unknown fields in request bodies.
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "22222222-2222-2222-2222-222222222222",
                    "actor_user_id": "33333333-3333-3333-3333-333333333333",
                }
            ]
        },
    )