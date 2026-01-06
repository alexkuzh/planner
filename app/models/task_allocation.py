# app/models/task_allocation.py
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaskAllocation(Base):
    __tablename__ = "task_allocations"
    __table_args__ = (
        # чтобы не задублировать одно и то же назначение в одну и ту же смену/день
        UniqueConstraint(
            "task_id", "work_date", "shift_code", "allocated_to",
            name="uq_task_alloc_task_date_shift_user"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    org_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # день, на который распределили
    work_date: Mapped[date] = mapped_column(Date, nullable=False)

    # смена: begin_of_week / end_of_week (пока просто строка, без таблицы shift_templates)
    shift_code: Mapped[str] = mapped_column(Text, nullable=False)

    # кому назначили (пока UUID пользователя; позже заменим на assignment_id)
    allocated_to: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # кто распределил (лид)
    allocated_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
