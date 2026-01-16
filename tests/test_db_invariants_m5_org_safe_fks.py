import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from datetime import date

from app.models.project_template import ProjectTemplate
from app.models.task import Task
from app.models.task_allocation import TaskAllocation
from app.models.deliverable import Deliverable


def _make_project(db, org_id):
    project_id = uuid.uuid4()
    p = ProjectTemplate(id=uuid.uuid4(), org_id=org_id, project_id=project_id)
    db.add(p)
    db.commit()
    return project_id


def _make_task(db, org_id, project_id, created_by):
    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="t",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
    )
    db.add(t)
    db.commit()
    return t


def _make_deliverable(db, org_id, project_id, created_by, serial):
    d = Deliverable(
        id=uuid.uuid4(),
        org_id=org_id,
        project_id=project_id,
        template_version_id=uuid.uuid4(),
        deliverable_type="product",
        serial=serial,
        status="in_progress",
        created_by=created_by,
    )
    db.add(d)
    db.commit()
    return d


def test_db_fk_task_allocations_must_match_task_org(db):
    org1 = uuid.uuid4()
    org2 = uuid.uuid4()
    created_by = uuid.uuid4()

    project1 = _make_project(db, org1)
    project2 = _make_project(db, org2)

    task_org1 = _make_task(db, org1, project1, created_by)

    # пытаемся создать allocation с org2, но task_id от org1 -> должно упасть
    a = TaskAllocation(
        id=uuid.uuid4(),
        org_id=org2,
        task_id=task_org1.id,
        user_id=uuid.uuid4(),
        role="executor",
    )
    db.add(a)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_fk_tasks_deliverable_must_match_org(db):
    org1 = uuid.uuid4()
    org2 = uuid.uuid4()
    created_by = uuid.uuid4()

    project1 = _make_project(db, org1)
    project2 = _make_project(db, org2)

    d_org2 = _make_deliverable(db, org2, project2, created_by, serial="D-ORG2")

    # task в org1, но deliverable_id из org2 -> должно упасть (после FK)
    t = Task(
        org_id=org1,
        project_id=project1,
        deliverable_id=d_org2.id,
        title="bad deliverable org",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
    )
    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()
