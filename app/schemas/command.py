# app/schemas/command.py
from typing import Generic, TypeVar
from pydantic import BaseModel
from uuid import UUID

T = TypeVar("T")

class Command(BaseModel, Generic[T]):
    expected_row_version: int
    client_event_id: UUID
    payload: T

    # B2: headers-first only; forbid legacy fields in body
    model_config = {"extra": "forbid"}
