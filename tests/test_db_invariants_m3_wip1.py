# tests/test_db_invariants_m3_wip1.py
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from tests.factories import make_project_template, make_task


def _now():
    return datetime.now(tz=timezone.utc)


def test_db_unique_wip1_one_active_task_per_assignee_per_org(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()
    assignee = uuid.uuid4()

    pt = make_project_template(db, org_id=org_id)
    project_id = pt.project_id

    # 1) первая активная задача на исполнителя — OK
    make_task(
        db,
        org_id=org_id,
        project_id=project_id,
        created_by=created_by,
        title="t1",
        status="assigned",
        assigned_to=assignee,
        assigned_at=_now(),
    )
    db.commit()

    # 2) вторая активная задача на того же исполнителя в том же org — должна упасть
    make_task(
        db,
        org_id=org_id,
        project_id=project_id,
        created_by=created_by,
        title="t2",
        status="in_progress",
        assigned_to=assignee,
        assigned_at=_now(),
    )

    with pytest.raises(IntegrityError):
        db.commit()
