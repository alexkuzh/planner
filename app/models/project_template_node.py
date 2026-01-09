from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.task import TaskKind


class ProjectTemplateNode(Base):
    __tablename__ = "project_template_nodes"
    __table_args__ = (
        UniqueConstraint("template_version_id", "code", name="uq_tpl_nodes_version_code"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    template_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # стабильный идентификатор узла внутри версии шаблона
    code: Mapped[str] = mapped_column(String, nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # дерево: храним parent_code (проще миграции/импорта)
    parent_code: Mapped[str | None] = mapped_column(String, nullable=True)

    kind: Mapped[str] = mapped_column(String, nullable=False, default=TaskKind.production.value)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_milestone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
