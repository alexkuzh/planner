# app/models/deliverable.py

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DeliverableStatus(str, enum.Enum):
    open = "open"
    submitted_to_qc = "submitted_to_qc"
    qc_rejected = "qc_rejected"
    qc_approved = "qc_approved"
    canceled = "canceled"


class Deliverable(Base):
    __tablename__ = "deliverables"
    __table_args__ = (
        UniqueConstraint("org_id", "serial", name="uq_deliverables_org_serial"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    org_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # тип изделия (chair/table/...), пока строкой
    deliverable_type: Mapped[str] = mapped_column(String, nullable=False)

    # серийник известен сразу
    serial: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=DeliverableStatus.open.value,
    )

    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
