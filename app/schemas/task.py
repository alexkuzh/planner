# app/schemas/task.py

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.task import TaskStatus, TaskKind


class TaskCreate(BaseModel):
    org_id: UUID
    project_id: UUID
    created_by: UUID
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    priority: int = 0
    deliverable_id: UUID | None = None
    is_milestone: bool = False

    # NEW:
    kind: TaskKind = TaskKind.production
    other_kind_label: str | None = None

    @model_validator(mode="after")
    def validate_other_kind_label(self):
        if self.kind == TaskKind.other:
            if not self.other_kind_label or not self.other_kind_label.strip():
                raise ValueError("other_kind_label is required when kind='other'")
        else:
            if self.other_kind_label:
                raise ValueError("other_kind_label is allowed only when kind='other'")

        if self.is_milestone and self.deliverable_id is None:
            raise ValueError("deliverable_id is required when is_milestone=true")

        return self


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    # Убираем статус, запрети менять status через общий PATCH
    # status: Optional[TaskStatus] = None
    deliverable_id: Optional[UUID] = None

class TaskRead(BaseModel):
    id: UUID
    org_id: UUID
    project_id: UUID
    created_by: UUID
    title: str
    description: str | None = None
    priority: int
    status: TaskStatus
    deliverable_id: UUID | None = None
    is_milestone: bool
    # NEW:
    kind: TaskKind
    other_kind_label: str | None = None

    row_version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskBlockerRead(BaseModel):
    id: UUID
    title: str
    status: str  # можно TaskStatus, но строка безопаснее пока status в модели text
    priority: int

    model_config = {"from_attributes": True}


class TaskDependencyCreate(BaseModel):
    predecessor_id: UUID


class TaskDependencyRead(BaseModel):
    predecessor_id: UUID
    successor_id: UUID
    created_by: UUID
    created_at: datetime
