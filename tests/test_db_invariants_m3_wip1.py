import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.task import Task
from app.models.project_template import ProjectTemplate


def _now():
    return datetime.now(timezone.utc)


def _make_project(db, org_id):
    project_id = uuid.uuid4()
    p = ProjectTemplate(id=uuid.uuid4(), org_id=org_id, project_id=project_id)
    db.add(p)
    db.commit()
    return project_id


def test_db_unique_wip1_one_active_task_per_assignee_per_org(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()
    assignee = uuid.uuid4()
    project_id = _make_project(db, org_id)

    # 1) первая активная задача на исполнителя — OK
    t1 = Task(
        org_id=org_id,
        project_id=project_id,
        title="t1",
        status="assigned",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=assignee,
        assigned_at=_now(),
    )
    db.add(t1)
    db.commit()

    # 2) вторая активная задача на того же исполнителя в том же org — должна упасть
    t2 = Task(
        org_id=org_id,
        project_id=project_id,
        title="t2",
        status="in_progress",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=assignee,
        assigned_at=_now(),
    )
    db.add(t2)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_unique_wip1_allows_multiple_tasks_if_not_active(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()
    assignee = uuid.uuid4()
    project_id = _make_project(db, org_id)

    # done — не активная, поэтому не считается в WIP
    t1 = Task(
        org_id=org_id,
        project_id=project_id,
        title="done",
        status="done",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=assignee,
        assigned_at=_now(),
    )
    db.add(t1)
    db.commit()

    # assigned — активная, допускается (т.к. done не блокирует)
    t2 = Task(
        org_id=org_id,
        project_id=project_id,
        title="assigned",
        status="assigned",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=assignee,
        assigned_at=_now(),
    )
    db.add(t2)
    db.commit()
