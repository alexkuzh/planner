import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _setup_project_and_deliverable(db: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
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

    return org_id, project_id, deliverable_id


def _insert_qc(
    db: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    result: str,
) -> uuid.UUID:
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
            "result": result,
        },
    )
    return qc_id


def test_m9_allows_single_qc_per_deliverable(db: Session):
    org_id, project_id, deliverable_id = _setup_project_and_deliverable(db)
    _insert_qc(
        db,
        org_id=org_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        result="rejected",
    )


def test_m9_forbids_second_qc_for_same_deliverable(db: Session):
    org_id, project_id, deliverable_id = _setup_project_and_deliverable(db)

    _insert_qc(
        db,
        org_id=org_id,
        project_id=project_id,
        deliverable_id=deliverable_id,
        result="rejected",
    )

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _insert_qc(
                db,
                org_id=org_id,
                project_id=project_id,
                deliverable_id=deliverable_id,
                result="approved",
            )
