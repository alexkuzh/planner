from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProjectTemplateVersion(Base):
    __tablename__ = "project_template_versions"
    __table_args__ = (
        UniqueConstraint("org_id", "project_id", "version", name="uq_tpl_versions_org_project_version"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    org_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Например: "v1", "v1.1", "2026-01-08"
    version: Mapped[str] = mapped_column(String, nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
