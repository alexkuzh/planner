from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProjectTemplateEdge(Base):
    __tablename__ = "project_template_edges"
    __table_args__ = (
        UniqueConstraint(
            "template_version_id",
            "predecessor_code",
            "successor_code",
            name="uq_tpl_edges_version_pred_succ",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    template_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    predecessor_code: Mapped[str] = mapped_column(String, nullable=False)
    successor_code: Mapped[str] = mapped_column(String, nullable=False)
