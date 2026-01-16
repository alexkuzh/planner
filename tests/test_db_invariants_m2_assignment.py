import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from app.models.project_template import ProjectTemplate
from app.models.task import Task

def _uids():
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _now():
    return datetime.now(timezone.utc)

def _make_project(db, org_id):
    project_id = uuid.uuid4()

    p = ProjectTemplate(
        id=uuid.uuid4(),
        org_id=org_id,
        project_id=project_id,
    )
    db.add(p)
    db.commit()

    return project_id


def test_db_ck_tasks_assignment_matches_status_blocked_cannot_have_assignee(db):
    (org_id, _, created_by, assignee) = _uids()
    project_id = _make_project(db, org_id)
    assert db.query(ProjectTemplate).filter_by(project_id=project_id).count() == 1

    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="blocked with assignee",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=assignee,
        assigned_at=_now(),
    )

    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_ck_tasks_assignment_matches_status_available_cannot_have_assignee(db):
    org_id, _, created_by, assignee = _uids()
    project_id = _make_project(db, org_id)
    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="available with assignee",
        status="available",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=assignee,
        assigned_at=_now(),
    )

    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_ck_tasks_assignment_matches_status_assigned_requires_assignee(db):
    org_id, _, created_by, _assignee = _uids()
    project_id = _make_project(db, org_id)
    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="assigned without assignee",
        status="assigned",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=None,
        assigned_at=None,
    )

    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_ck_tasks_assignment_matches_status_in_progress_requires_assignee(db):
    org_id, _, created_by, _assignee = _uids()
    project_id = _make_project(db, org_id)
    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="in_progress without assignee",
        status="in_progress",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=None,
        assigned_at=None,
    )

    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_ck_tasks_assignment_matches_status_submitted_requires_assignee(db):
    org_id, _, created_by, _assignee = _uids()
    project_id = _make_project(db, org_id)
    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="submitted without assignee",
        status="submitted",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=None,
        assigned_at=None,
    )

    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_ck_tasks_assignment_matches_status_done_allows_any_assignment_shape(db):
    org_id, _, created_by, assignee = _uids()
    project_id = _make_project(db, org_id)
    # done + no assignee (allowed)
    t1 = Task(
        org_id=org_id,
        project_id=project_id,
        title="done no assignee",
        status="done",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=None,
        assigned_at=None,
    )
    db.add(t1)
    db.commit()

    # done + assignee present (also allowed; we keep it flexible for history)
    t2 = Task(
        org_id=org_id,
        project_id=project_id,
        title="done with assignee",
        status="done",
        kind="production",
        created_by=created_by,
        priority=0,
        assigned_to=assignee,
        assigned_at=_now(),
    )
    db.add(t2)
    db.commit()

