#app/schemas/task.py

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from uuid import UUID

from app.models.task import TaskStatus

class TaskCreate(BaseModel):
    org_id: UUID
    project_id: UUID
    created_by: UUID
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    priority: int = 0


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    # Убираем статус, запрети менять status через общий PATCH
    #status: Optional[TaskStatus] = None


class TaskRead(BaseModel):
    id: UUID
    org_id: UUID
    project_id: UUID
    created_by: UUID
    title: str
    description: str | None = None
    priority: int
    status: TaskStatus
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