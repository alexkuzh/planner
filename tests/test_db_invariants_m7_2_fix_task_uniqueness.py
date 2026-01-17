import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _setup_project_deliverable_qc_origin_task(db: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """
    Создаёт минимальный набор данных для fix-task (qc_reject):
      - project_templates (для FK tasks.project_id и task_transitions.project_id)
      - deliverable
      - qc_inspection (требует deliverable_id)
      - origin (work) task

    Возвращает: (org_id, project_id, deliverable_id, qc_id, origin_task_id)
    """
    org_id = _uuid()
    project_id = _uuid()

    db.execute(
        text(
            """
            INSERT INTO project_templates (id, org_id, project_id, active_template_version_id, updated_by)
            VALUES (:id, :org_id, :project_id, NULL, NULL)
            """
        ),
        {"id": _uuid(), "org_id": org_id, "project_id": project_id},
    )

    deliverable_id = _uuid()
    db.execute(
        text(
            """
            INSERT INTO deliverables (id, org_id, project_id, deliverable_type, serial, status, created_by)
            VALUES (:id, :org_id, :project_id, :deliverable_type, :serial, :status, :created_by)
            """
        ),
        {
            "id": deliverable_id,
            "org_id": org_id,
            "project_id": project_id,
            "deliverable_type": "chair",
            "serial": f"SN-{_uuid()}",
            "status": "open",
            "created_by": _uuid(),
        },
    )

    qc_id = _uuid()
    db.execute(
        text(
            """
            INSERT INTO qc_inspections (id, org_id, project_id, deliverable_id, inspector_user_id, result)
            VALUES (:id, :org_id, :project_id, :deliverable_id, :inspector_user_id, :result)
            """
        ),
        {
            "id": qc_id,
            "org_id": org_id,
            "project_id": project_id,
            "deliverable_id": deliverable_id,
            "inspector_user_id": _uuid(),
            "result": "rejected",
        },
    )

    origin_task_id = _uuid()
    # work_kind='work' => origin_task_id/fix_source/fix_severity/qc_inspection_id MUST be NULL (см ck_tasks_fix_fields_consistent)
    db.execute(
        text(
            """
            INSERT INTO tasks (id, org_id, project_id, title, kind, status, created_by, work_kind)
            VALUES (:id, :org_id, :project_id, :title, :kind, :status, :created_by, CAST(:work_kind AS work_kind))
            """
        ),
        {
            "id": origin_task_id,
            "org_id": org_id,
            "project_id": project_id,
            "title": "Origin work task",
            "kind": "production",
            "status": "available",
            "created_by": _uuid(),
            "work_kind": "work",
        },
    )

    return org_id, project_id, deliverable_id, qc_id, origin_task_id


def _insert_fix_task_qc_reject(
    db: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    origin_task_id: uuid.UUID,
    qc_id: uuid.UUID,
) -> uuid.UUID:
    fix_task_id = _uuid()
    db.execute(
        text(
            """
            INSERT INTO tasks (
                id, org_id, project_id,
                title, kind, status, created_by,
                work_kind, origin_task_id, fix_source, fix_severity, qc_inspection_id
            )
            VALUES (
                :id, :org_id, :project_id,
                :title, :kind, :status, :created_by,
                CAST(:work_kind AS work_kind),
                :origin_task_id,
                CAST(:fix_source AS fix_source),
                CAST(:fix_severity AS fix_severity),
                :qc_inspection_id
            )
            """
        ),
        {
            "id": fix_task_id,
            "org_id": org_id,
            "project_id": project_id,
            "title": "Fix task",
            "kind": "production",
            "status": "available",
            "created_by": _uuid(),
            "work_kind": "fix",
            "origin_task_id": origin_task_id,
            "fix_source": "qc_reject",
            "fix_severity": "minor",
            "qc_inspection_id": qc_id,
        },
    )
    return fix_task_id


def _insert_fix_task_other_source(
    db: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    origin_task_id: uuid.UUID,
) -> uuid.UUID:
    """
    Для fix_source != qc_reject qc_inspection_id MUST be NULL (см ck_tasks_fix_fields_consistent).
    """
    fix_task_id = _uuid()
    db.execute(
        text(
            """
            INSERT INTO tasks (
                id, org_id, project_id,
                title, kind, status, created_by,
                work_kind, origin_task_id, fix_source, fix_severity, qc_inspection_id
            )
            VALUES (
                :id, :org_id, :project_id,
                :title, :kind, :status, :created_by,
                CAST(:work_kind AS work_kind),
                :origin_task_id,
                CAST(:fix_source AS fix_source),
                CAST(:fix_severity AS fix_severity),
                NULL
            )
            """
        ),
        {
            "id": fix_task_id,
            "org_id": org_id,
            "project_id": project_id,
            "title": "Fix task other source",
            "kind": "production",
            "status": "available",
            "created_by": _uuid(),
            "work_kind": "fix",
            "origin_task_id": origin_task_id,
            "fix_source": "worker_initiative",
            "fix_severity": "minor",
        },
    )
    return fix_task_id


def test_m7_2_allows_single_fix_task_for_qc_reject(db: Session):
    org_id, project_id, _deliverable_id, qc_id, origin_task_id = _setup_project_deliverable_qc_origin_task(db)

    _insert_fix_task_qc_reject(
        db,
        org_id=org_id,
        project_id=project_id,
        origin_task_id=origin_task_id,
        qc_id=qc_id,
    )


def test_m7_2_forbids_second_fix_task_for_same_origin_qc_reject(db: Session):
    org_id, project_id, _deliverable_id, qc_id, origin_task_id = _setup_project_deliverable_qc_origin_task(db)

    _insert_fix_task_qc_reject(
        db,
        org_id=org_id,
        project_id=project_id,
        origin_task_id=origin_task_id,
        qc_id=qc_id,
    )

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _insert_fix_task_qc_reject(
                db,
                org_id=org_id,
                project_id=project_id,
                origin_task_id=origin_task_id,
                qc_id=qc_id,
            )


def test_m7_2_partial_unique_does_not_block_other_fix_sources(db: Session):
    org_id, project_id, _deliverable_id, qc_id, origin_task_id = _setup_project_deliverable_qc_origin_task(db)

    _insert_fix_task_qc_reject(
        db,
        org_id=org_id,
        project_id=project_id,
        origin_task_id=origin_task_id,
        qc_id=qc_id,
    )

    # другой fix_source для того же origin_task_id должен быть допустим
    _insert_fix_task_other_source(
        db,
        org_id=org_id,
        project_id=project_id,
        origin_task_id=origin_task_id,
    )
