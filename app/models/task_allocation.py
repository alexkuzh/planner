from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaskAllocation(Base):
    __tablename__ = "task_allocations"
    __table_args__ = (
        # опционально: если хочешь защититься от дублей одного назначения
        # (в текущей таблице нет work_date/shift_code, поэтому уникальность только такая)
        UniqueConstraint("org_id", "task_id", "user_id", "role", name="uq_task_alloc_org_task_user_role"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    org_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
