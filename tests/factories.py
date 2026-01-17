# tests/factories.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.task import Task
from app.models.task_allocation import TaskAllocation
from app.models.deliverable import Deliverable
from app.models.qc_inspection import QcInspection
from app.models.project_template import ProjectTemplate


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def make_project_template(
    db,
    *,
    org_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    flush: bool = True,
    **overrides: Any,
) -> ProjectTemplate:
    """
    Обязательная сущность для FK:
      tasks.project_id -> project_templates(project_id)
    """
    org_id = org_id or uuid.uuid4()
    project_id = project_id or uuid.uuid4()

    pt = ProjectTemplate(
        id=overrides.pop("id", uuid.uuid4()),
        org_id=org_id,
        project_id=project_id,
        **overrides,
    )
    db.add(pt)
    if flush:
        db.flush()
    return pt


def make_task(
    db,
    *,
    org_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    status: str = "blocked",
    assigned_to: uuid.UUID | None = None,
    assigned_at: datetime | None = None,
    flush: bool = False,
    **overrides: Any,
) -> Task:
    """
    Task по умолчанию:
      - status='blocked'
      - assigned_to=None
    => не нарушает M2.

    ВАЖНО: не задаём created_at/updated_at руками — это зона ответственности БД.
    По умолчанию flush=False, чтобы тест сам контролировал, где ловить IntegrityError.
    """
    org_id = org_id or uuid.uuid4()
    project_id = project_id or uuid.uuid4()
    created_by = created_by or uuid.uuid4()

    task = Task(
        id=overrides.pop("id", uuid.uuid4()),
        org_id=org_id,
        project_id=project_id,
        deliverable_id=overrides.pop("deliverable_id", None),
        title=overrides.pop("title", "test task"),
        description=overrides.pop("description", None),
        status=status,
        priority=overrides.pop("priority", 0),
        kind=overrides.pop("kind", "production"),
        other_kind_label=overrides.pop("other_kind_label", None),
        work_kind=overrides.pop("work_kind", "work"),
        is_milestone=overrides.pop("is_milestone", False),
        created_by=created_by,
        assigned_to=assigned_to,
        assigned_at=assigned_at,
        parent_task_id=overrides.pop("parent_task_id", None),
        fix_reason=overrides.pop("fix_reason", None),
        origin_task_id=overrides.pop("origin_task_id", None),
        qc_inspection_id=overrides.pop("qc_inspection_id", None),
        minutes_spent=overrides.pop("minutes_spent", None),
        fix_severity=overrides.pop("fix_severity", None),
        fix_source=overrides.pop("fix_source", None),
        row_version=overrides.pop("row_version", 1),
        **overrides,
    )
    db.add(task)
    if flush:
        db.flush()
    return task


def make_allocation(
    db,
    *,
    org_id: uuid.UUID,
    task_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    role: str = "executor",
    flush: bool = True,
    **overrides: Any,
) -> TaskAllocation:
    """
    Реальная схема task_allocations:
      id, org_id, task_id, user_id, role, created_at
    """
    alloc = TaskAllocation(
        id=overrides.pop("id", uuid.uuid4()),
        org_id=org_id,
        task_id=task_id,
        user_id=user_id or uuid.uuid4(),
        role=role,
        **overrides,
    )
    db.add(alloc)
    if flush:
        db.flush()
    return alloc


def make_deliverable(
    db,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    serial: str | None = None,
    template_version_id: uuid.UUID | None = None,
    deliverable_type: str = "product",
    status: str = "in_progress",
    flush: bool = True,
    **overrides,
):
    d = Deliverable(
        id=overrides.pop("id", uuid.uuid4()),
        org_id=org_id,
        project_id=project_id,
        template_version_id=template_version_id or uuid.uuid4(),
        deliverable_type=deliverable_type,
        serial=serial or f"D-{uuid.uuid4().hex[:8]}",
        status=status,
        created_by=created_by,
        **overrides,
    )
    db.add(d)
    if flush:
        db.flush()
    return d



def make_qc_inspection(
    db,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    inspector_user_id: uuid.UUID | None = None,
    result: str = "rejected",
    flush: bool = True,
    **overrides,
):
    qc = QcInspection(
        id=overrides.pop("id", uuid.uuid4()),
        org_id=org_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        inspector_user_id=inspector_user_id or uuid.uuid4(),
        result=result,
        **overrides,
    )
    db.add(qc)
    if flush:
        db.flush()
    return qc


