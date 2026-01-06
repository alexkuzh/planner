from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.deliverable_signoff import SignoffResult


class DeliverableSignoffCreate(BaseModel):
    org_id: UUID
    project_id: UUID
    signed_off_by: UUID

    result: SignoffResult = SignoffResult.approved
    comment: str | None = Field(default=None, max_length=1000)


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
