from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal, List

class FixSeverity(str, Enum):
    minor = "minor"
    major = "major"
    critical = "critical"

class FixSource(str, Enum):
    qc_reject = "qc_reject"
    worker_initiative = "worker_initiative"
    supervisor_request = "supervisor_request"

class FixAttachment(BaseModel):
    kind: Literal["photo_before", "photo_after", "photo", "doc", "link"]
    url: str
    comment: Optional[str] = None

class ReportFixPayload(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=4000)
    severity: FixSeverity = FixSeverity.minor
    minutes_spent: Optional[int] = Field(None, ge=0, le=24*60)
    attachments: List[FixAttachment] = []

class DeliverableFixPayload(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=4000)
    severity: FixSeverity = FixSeverity.minor
    minutes_spent: Optional[int] = Field(None, ge=0, le=24*60)
    attachments: List[FixAttachment] = []
