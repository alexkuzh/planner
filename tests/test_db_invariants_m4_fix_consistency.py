# tests/test_db_invariants_m4_fix_consistency.py
import uuid
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.task import Task

from tests.factories import (
    make_project_template,
    make_task,
    make_deliverable,
    make_qc_inspection,
)


def test_db_ck_fix_fields_work_task_must_not_have_fix_columns(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()

    pt = make_project_template(db, org_id=org_id)

    t = make_task(
        db,
        org_id=org_id,
        project_id=pt.project_id,
        created_by=created_by,
        status="blocked",
        kind="production",
        priority=0,
        work_kind="work",
        fix_source="qc_reject",  # ❌ invalid for work
        flush=False,
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_db_ck_fix_fields_fix_task_requires_origin_and_fix_meta(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()

    pt = make_project_template(db, org_id=org_id)

    origin = make_task(
        db,
        org_id=org_id,
        project_id=pt.project_id,
        created_by=created_by,
        status="blocked",
        kind="production",
        priority=0,
        work_kind="work",
        flush=False,
    )
    db.commit()

    # fix-task requires origin_task_id + fix_source + fix_severity
    make_task(
        db,
        org_id=org_id,
        project_id=pt.project_id,
        created_by=created_by,
        status="blocked",
        kind="production",
        priority=0,
        work_kind="fix",
        origin_task_id=origin.id,
        fix_source=None,      # ❌ invalid
        fix_severity=None,    # ❌ invalid
        flush=False,
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_db_ck_fix_fields_qc_reject_requires_qc_inspection_id(db):
    org_id = uuid.uuid4()
    created_by = uuid.uuid4()
    inspector = uuid.uuid4()

    # --- project для первого (невалидного) кейса ---
    pt1 = make_project_template(db, org_id=org_id)
    deliverable1 = make_deliverable(db, org_id=org_id, project_id=pt1.project_id, created_by=created_by)
    qc1 = make_qc_inspection(
        db,
        org_id=org_id,
        project_id=pt1.project_id,
        deliverable_id=deliverable1.id,
        inspector_user_id=inspector,
        result="rejected",
    )

    origin1 = make_task(
        db,
        org_id=org_id,
        project_id=pt1.project_id,
        created_by=created_by,
        status="blocked",
        kind="production",
        priority=0,
        work_kind="work",
        flush=False,
    )
    db.commit()

    # invalid: qc_reject but qc_inspection_id is NULL
    t = Task(
        org_id=org_id,
        project_id=pt1.project_id,
        title="fix-qc-reject-missing-qc_id",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
        work_kind="fix",
        origin_task_id=origin1.id,
        fix_source="qc_reject",
        fix_severity="minor",
        qc_inspection_id=None,  # ❌ invalid
    )
    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()

    # --- project для валидного кейса (НОВЫЙ!) ---
    pt2 = make_project_template(db, org_id=org_id)
    deliverable2 = make_deliverable(db, org_id=org_id, project_id=pt2.project_id, created_by=created_by)
    qc2 = make_qc_inspection(
        db,
        org_id=org_id,
        project_id=pt2.project_id,
        deliverable_id=deliverable2.id,
        inspector_user_id=inspector,
        result="rejected",
    )

    origin2 = make_task(
        db,
        org_id=org_id,
        project_id=pt2.project_id,
        created_by=created_by,
        status="blocked",
        kind="production",
        priority=0,
        work_kind="work",
        flush=False,
    )
    db.commit()

    t2 = Task(
        org_id=org_id,
        project_id=pt2.project_id,
        title="fix-qc-reject-ok",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
        work_kind="fix",
        origin_task_id=origin2.id,
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

    pt = make_project_template(db, org_id=org_id)
    deliverable = make_deliverable(db, org_id=org_id, project_id=pt.project_id, created_by=created_by)
    qc = make_qc_inspection(
        db,
        org_id=org_id,
        project_id=pt.project_id,
        deliverable_id=deliverable.id,
        inspector_user_id=inspector,
        result="rejected",
    )

    # invalid: qc_inspection_id set, but work_kind is work
    t = Task(
        org_id=org_id,
        project_id=pt.project_id,
        title="work-has-qc_id",
        status="blocked",
        kind="production",
        created_by=created_by,
        priority=0,
        work_kind="work",
        qc_inspection_id=qc.id,  # ❌ invalid
    )
    db.add(t)
    with pytest.raises(IntegrityError):
        db.commit()
