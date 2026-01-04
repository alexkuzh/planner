from pydantic import BaseModel, Field


class TaskTransitionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=50)
