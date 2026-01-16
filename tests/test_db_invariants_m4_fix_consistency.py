import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.project_template import ProjectTemplate
from app.models.task import Task
from app.models.qc_inspection import QcInspection
from app.models.deliverable import Deliverable

def _now():
    return datetime.now(timezone.utc)


def _make_project(db, org_id):
    project_id = uuid.uuid4()
    p = ProjectTemplate(id=uuid.uuid4(), org_id=org_id, project_id=project_id)
    db.add(p)
    db.commit()
    return project_id

def _make_deliverable(db, org_id, project_id, created_by):
    d = Deliverable(
        id=uuid.uuid4(),
        org_id=org_id,
        project_id=project_id,
        template_version_id=uuid.uuid4(),
        deliverable_type="product",
        serial="D-1",
        status="in_progress",
        created_by=created_by,
    )
    db.add(d)
    db.commit()
    return d

def _make_base_task(db, org_id, project_id, created_by, status="blocked"):
    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="base",
        status=status,
        kind="production",
        created_by=created_by,
        priority=0,
    )
    db.add(t)
    db.commit()
    return t


def _make_qc_inspection(db, org_id, project_id, inspector_user_id, deliverable_id, result="rejected"):
    qc = QcInspection(
        id=uuid.uuid4(),
        org_id=org_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        inspector_user_id=inspector_user_id,
        result=result,
    )
    db.add(qc)
    db.commit()
    return qc


def test_db_ck_fix_fields_work_task_must_not_have_fix_columns(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()
    project_id = _make_project(db, org_id)

    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="work-but-has-fix",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
        work_kind="work",
        fix_source="qc_reject",
    )
    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_ck_fix_fields_fix_task_requires_origin_and_fix_meta(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()
    project_id = _make_project(db, org_id)

    origin = _make_base_task(db, org_id, project_id, created_by)

    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="fix-missing-meta",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
        work_kind="fix",
        origin_task_id=origin.id,
        fix_source=None,      # invalid
        fix_severity=None,    # invalid
    )
    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()


def test_db_ck_fix_fields_qc_reject_requires_qc_inspection_id(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()
    inspector = uuid.uuid4()

    # --- project для первого (невалидного) кейса ---
    project_id_1 = _make_project(db, org_id)

    deliverable = _make_deliverable(db, org_id, project_id_1, created_by)
    qc = _make_qc_inspection(
        db,
        org_id,
        project_id_1,
        inspector,
        deliverable_id=deliverable.id,
        result="rejected",
    )
    qc_id = qc.id

    origin1 = _make_base_task(db, org_id, project_id_1, created_by)
    origin1_id = origin1.id

    t = Task(
        org_id=org_id,
        project_id=project_id_1,
        title="fix-qc-reject-missing-qc_id",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
        work_kind="fix",
        origin_task_id=origin1_id,
        fix_source="qc_reject",
        fix_severity="minor",
        qc_inspection_id=None,  # ❌ invalid
    )
    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()

    # ⚠️ rollback уничтожает project_template
    db.rollback()

    # --- project для валидного кейса (НОВЫЙ!) ---
    project_id_2 = _make_project(db, org_id)

    deliverable2 = _make_deliverable(db, org_id, project_id_2, created_by)
    qc2 = _make_qc_inspection(
        db,
        org_id,
        project_id_2,
        inspector,
        deliverable_id=deliverable2.id,
        result="rejected",
    )

    origin2 = _make_base_task(db, org_id, project_id_2, created_by)
    origin2_id = origin2.id

    t2 = Task(
        org_id=org_id,
        project_id=project_id_2,
        title="fix-qc-reject-ok",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
        work_kind="fix",
        origin_task_id=origin2_id,
        fix_source="qc_reject",
        fix_severity="minor",
        qc_inspection_id=qc2.id,  # ✅ valid
    )
    db.add(t2)
    db.commit()




def test_db_ck_fix_fields_qc_inspection_id_requires_fix_qc_reject(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()
    inspector = uuid.uuid4()
    project_id = _make_project(db, org_id)

    deliverable = _make_deliverable(db, org_id, project_id, created_by)
    qc = _make_qc_inspection(
        db,
        org_id,
        project_id,
        inspector,
        deliverable_id=deliverable.id,
        result="rejected",
    )

    # invalid: qc_inspection_id set, but work_kind is work
    t = Task(
        org_id=org_id,
        project_id=project_id,
        title="work-has-qc_id",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
        work_kind="work",
        qc_inspection_id=qc.id,
    )
    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()
