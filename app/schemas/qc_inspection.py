from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.qc_inspection import QcResult


class QcDecisionRequest(BaseModel):
    org_id: UUID
    project_id: UUID
    inspector_user_id: UUID

    result: QcResult
    notes: str | None = Field(default=None, max_length=2000)


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
