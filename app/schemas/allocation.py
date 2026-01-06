from datetime import date
from uuid import UUID
from pydantic import BaseModel, Field


class AllocationItem(BaseModel):
    task_id: UUID
    allocated_to: UUID
    note: str | None = None


class AllocationBatchRequest(BaseModel):
    org_id: UUID
    project_id: UUID
    work_date: date
    shift_code: str = Field(pattern="^(begin_of_week|end_of_week)$")
    allocations: list[AllocationItem] = Field(min_length=1)


class AllocationOut(BaseModel):
    id: UUID
    org_id: UUID
    project_id: UUID
    task_id: UUID
    work_date: date
    shift_code: str
    allocated_to: UUID
    allocated_by: UUID
    note: str | None = None

    # NEW: чтобы лид видел, на какое изделие задача
    deliverable_id: UUID | None = None
    deliverable_type: str | None = None
    deliverable_serial: str | None = None

