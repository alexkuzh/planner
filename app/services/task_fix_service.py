from sqlalchemy.orm import Session
from uuid import UUID
from app.models.task import Task, TaskKind, FixSource, FixSeverity, WorkKind


class TaskFixService:
    def __init__(self, db: Session):
        self.db = db

    def create_initiative_fix_for_task(
        self,
        origin_task: Task,
        actor_user_id: UUID,
        title: str,
        description: str | None,
        severity: FixSeverity,
        minutes_spent: int | None,
        attachments: list[dict],
    ) -> Task:
        fix = Task(
            org_id=origin_task.org_id,
            deliverable_id=origin_task.deliverable_id,
            parent_task_id=None,  # фикс обычно не часть WBS; можно сделать под origin_task.parent если хочешь
            title=title,
            description=description,
            kind=TaskKind.fix,
            origin_task_id=origin_task.id,
            qc_inspection_id=None,
            fix_source=FixSource.worker_initiative,
            fix_severity=severity,
            minutes_spent=minutes_spent,
            created_by=actor_user_id,
        )
        self.db.add(fix)
        self.db.flush()

        # attachments: на MVP можно писать в task_event payload или отдельную таблицу
        # здесь оставляю как TODO.

        return fix

    def create_qc_reject_fix(
        self,
        deliverable_id: UUID,
        org_id: UUID,
        actor_user_id: UUID,
        qc_inspection_id: UUID,
        title: str,
        description: str | None,
        responsible_user_id: UUID | None,
    ) -> Task:
        fix = Task(
            org_id=org_id,
            deliverable_id=deliverable_id,
            title=title,
            description=description,
            kind=TaskKind.fix,
            origin_task_id=None,
            qc_inspection_id=qc_inspection_id,
            fix_source=FixSource.qc_reject,
            fix_severity=FixSeverity.major,  # разумный дефолт для QC reject
            minutes_spent=None,
            created_by=actor_user_id,
            # optional: assigned_to = responsible_user_id
        )
        self.db.add(fix)
        self.db.flush()
        return fix

def validate_fix_task(task: Task) -> None:
    if task.work_kind == WorkKind.fix:
        if task.fix_source is None:
            raise ValueError("fix_source is required for fix-task")
        if task.fix_severity is None:
            raise ValueError("fix_severity is required for fix-task")
    else:
        if task.fix_source is not None or task.fix_severity is not None:
            raise ValueError("fix_* fields must be NULL for non-fix tasks")
