from pydantic import BaseModel

from app.schemas.deliverable import DeliverableRead
from app.schemas.task import TaskRead
from app.schemas.deliverable_signoff import DeliverableSignoffRead
from app.schemas.qc_inspection import QcInspectionRead


class DeliverableDashboard(BaseModel):
    deliverable: DeliverableRead
    tasks: list[TaskRead]

    last_signoff: DeliverableSignoffRead | None = None
    last_qc_inspection: QcInspectionRead | None = None
