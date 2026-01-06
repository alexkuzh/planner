from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QcResult(str, enum.Enum):
    approved = "approved"
    rejected = "rejected"


class QcInspection(Base):
    __tablename__ = "qc_inspections"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    org_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    deliverable_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    inspector_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # кто несёт ответственность за качество (обычно: кто подписал выпуск production sign-off)
    responsible_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    result: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
