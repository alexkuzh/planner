from uuid import UUID
from pydantic import BaseModel


class SubmitToQcRequest(BaseModel):
    org_id: UUID
    project_id: UUID
    actor_user_id: UUID
