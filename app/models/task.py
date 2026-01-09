# app/models/task.py
from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TaskStatus(str, enum.Enum):
    new = "new"
    planned = "planned"
    assigned = "assigned"
    in_progress = "in_progress"
    in_review = "in_review"
    rejected = "rejected"
    done = "done"
    canceled = "canceled"


class TaskKind(str, enum.Enum):
    """Доменная классификация задачи: production/maintenance/admin/other.
    Это НЕ про work/fix.
    """
    production = "production"
    maintenance = "maintenance"
    admin = "admin"
    other = "other"


class WorkKind(str, enum.Enum):
    """Тип работы: обычная работа или исправление (fix-task)."""
    work = "work"
    fix = "fix"


class FixSeverity(str, enum.Enum):
    minor = "minor"
    major = "major"
    critical = "critical"


class FixSource(str, enum.Enum):
    qc_reject = "qc_reject"
    worker_initiative = "worker_initiative"
    supervisor_request = "supervisor_request"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    org_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # NULL = задача не относится к конкретному deliverable (maintenance/admin/other)
    deliverable_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # В БД у тебя text/string — оставляем так, но используем TaskStatus values
    status: Mapped[str] = mapped_column(String, nullable=False, default=TaskStatus.new.value)

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Доменная классификация (production/maintenance/admin/other)
    # Оставляем String, чтобы совпадать с текущей БД и не ломать данные.
    kind: Mapped[str] = mapped_column(String, nullable=False, default=TaskKind.production.value)

    other_kind_label: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Новый признак: work vs fix (для бонусов/аналитики/рефакторинга)
    work_kind: Mapped[WorkKind] = mapped_column(
        SAEnum(WorkKind, name="work_kind"),
        nullable=False,
        default=WorkKind.work,
    )

    is_milestone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    assigned_to: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # WBS дерево
    parent_task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Опционально: если хочешь хранить отдельную причину фикса, иначе используй description
    fix_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- fix-task связи (ортогонально к WBS) ----
    origin_task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    origin_task: Mapped[Optional["Task"]] = relationship(
        "Task",
        remote_side="Task.id",
        foreign_keys=[origin_task_id],
    )

    qc_inspection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("qc_inspections.id", ondelete="SET NULL"),
        nullable=True,
    )

    minutes_spent: Mapped[int | None] = mapped_column(Integer, nullable=True)

    fix_severity: Mapped[FixSeverity | None] = mapped_column(
        SAEnum(FixSeverity, name="fix_severity"),
        nullable=True,
    )
    fix_source: Mapped[FixSource | None] = mapped_column(
        SAEnum(FixSource, name="fix_source"),
        nullable=True,
    )

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

    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
