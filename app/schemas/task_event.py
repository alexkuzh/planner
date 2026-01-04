from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskEventRead(BaseModel):
    id: int
    task_id: int
    action: str
    from_status: str
    to_status: str
    actor: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
