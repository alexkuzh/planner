import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.task import Task
from app.models.qc_inspection import QcInspection


def _uids():
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def test_db_check_tasks_status_allowed_values(db):
    org_id, project_id, created_by = _uids()

    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="Bad status",
        status="lol",
        kind="production",
        created_by=created_by,
        priority=0,
    )

    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_check_qc_inspections_result_allowed_values(db):
    org_id, project_id, inspector_user_id = _uids()
    deliverable_id = uuid.uuid4()

    qc = QcInspection(
        org_id=org_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        inspector_user_id=inspector_user_id,
        result="nope",
    )

    db.add(qc)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_check_tasks_priority_nonneg(db):
    org_id, project_id, created_by = _uids()

    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="Negative priority",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=-1,
    )

    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()
