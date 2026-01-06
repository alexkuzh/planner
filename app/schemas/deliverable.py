from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.deliverable import DeliverableStatus


class DeliverableCreate(BaseModel):
    org_id: UUID
    project_id: UUID
    created_by: UUID

    deliverable_type: str = Field(min_length=1, max_length=64)
    serial: str = Field(min_length=1, max_length=120)


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
