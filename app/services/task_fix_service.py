# app/services/task_fix_service.py

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.deliverable import Deliverable
from app.models.task import (
    Task,
    TaskKind,
    TaskStatus,
    WorkKind,
    FixSource,
    FixSeverity,
)


class TaskFixService:
    """
    Единственная точка создания fix-task.
    Инвариант: work_kind=fix => fix_source и fix_severity обязательны.
    """

    def __init__(self, db: Session):
        self.db = db

    # ---------- Public API ----------

    def create_initiative_fix_for_task(
        self,
        origin_task: Task,
        actor_user_id: UUID,
        title: str,
        description: str | None,
        severity: FixSeverity,
        minutes_spent: int | None,
        attachments: list[dict] | None = None,
    ) -> Task:
        """
        Работник инициирует фикс, привязанный к конкретной задаче (origin_task).
        """
        return self.create_fix(
            org_id=origin_task.org_id,
            project_id=origin_task.project_id,
            deliverable_id=origin_task.deliverable_id,
            actor_user_id=actor_user_id,
            title=title,
            description=description,
            source=FixSource.worker_initiative,
            severity=severity,
            minutes_spent=minutes_spent,
            origin_task_id=origin_task.id,
            qc_inspection_id=None,
            attachments=attachments,
        )

    def create_initiative_fix_for_deliverable(
        self,
        deliverable: Deliverable,
        actor_user_id: UUID,
        title: str,
        description: str | None,
        severity: FixSeverity,
        minutes_spent: int | None,
        attachments: list[dict] | None = None,
    ) -> Task:
        """
        Работник инициирует фикс по изделию (без привязки к конкретной задаче).
        """
        return self.create_fix(
            org_id=deliverable.org_id,
            project_id=deliverable.project_id,
            deliverable_id=deliverable.id,
            actor_user_id=actor_user_id,
            title=title,
            description=description,
            source=FixSource.worker_initiative,
            severity=severity,
            minutes_spent=minutes_spent,
            origin_task_id=None,
            qc_inspection_id=None,
            attachments=attachments,
        )

    def create_qc_reject_fix(
        self,
        deliverable: Deliverable,
        actor_user_id: UUID,
        qc_inspection_id: UUID,
        title: str,
        description: str | None,
        severity: FixSeverity = FixSeverity.major,
        minutes_spent: int | None = None,
        attachments: list[dict] | None = None,
    ) -> Task:
        """
        QC reject создаёт fix-task по изделию. origin_task отсутствует.
        """
        return self.create_fix(
            org_id=deliverable.org_id,
            project_id=deliverable.project_id,
            deliverable_id=deliverable.id,
            actor_user_id=actor_user_id,
            title=title,
            description=description,
            source=FixSource.qc_reject,
            severity=severity,
            minutes_spent=minutes_spent,
            origin_task_id=None,
            qc_inspection_id=qc_inspection_id,
            attachments=attachments,
        )

    def create_fix(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        deliverable_id: UUID | None,
        actor_user_id: UUID,
        title: str,
        description: str | None,
        source: FixSource,
        severity: FixSeverity,
        minutes_spent: int | None = None,
        origin_task_id: UUID | None = None,
        qc_inspection_id: UUID | None = None,
        attachments: list[dict] | None = None,
    ) -> Task:
        """
        Ядро создания fix-task. Все остальные методы должны вызывать только его.

        deliverable_id может быть None только если вы сознательно разрешаете fix без изделия.
        Для вашего домена (MVP) обычно deliverable_id должен быть НЕ None.
        """
        if deliverable_id is None:
            # В вашем домене fix почти всегда относится к изделию.
            raise ValueError("Invariant violated: fix-task must be linked to a deliverable_id")

        fix = Task(
            org_id=org_id,
            project_id=project_id,
            deliverable_id=deliverable_id,
            created_by=actor_user_id,
            title=title,
            description=description,
            status=TaskStatus.new.value,
            kind=TaskKind.production.value,  # единый дефолт для fix в MVP
            work_kind=WorkKind.fix,
            parent_task_id=None,
            origin_task_id=origin_task_id,
            qc_inspection_id=qc_inspection_id,
            fix_source=source,
            fix_severity=severity,
            minutes_spent=minutes_spent,
        )

        self._validate_fix_fields(fix)

        self.db.add(fix)
        self.db.flush()  # гарантирует fix.id

        # attachments: на MVP можно писать в task_event payload или отдельную таблицу.
        # Здесь оставляем как TODO.
        _ = attachments  # чтобы не ругались линтеры, если используешь

        return fix

    # ---------- Invariants ----------

    def _validate_fix_fields(self, task: Task) -> None:
        """
        Инвариант:
        - work_kind=fix => fix_source и fix_severity обязательны
        - work_kind!=fix => fix_* должны быть NULL
        """
        if task.work_kind == WorkKind.fix:
            if task.fix_source is None:
                raise ValueError("Invariant violated: fix-task requires fix_source")
            if task.fix_severity is None:
                raise ValueError("Invariant violated: fix-task requires fix_severity")
        else:
            if task.fix_source is not None or task.fix_severity is not None:
                raise ValueError("Invariant violated: fix_* fields must be NULL for non-fix tasks")
