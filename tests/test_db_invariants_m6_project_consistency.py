import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _create_two_projects_same_org(db: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """
    Создаёт 2 project_templates в одном org, чтобы можно было вставлять tasks/deliverables/qc/signoffs.
    project_id уникален глобально, поэтому генерим новые UUID.
    """
    org_id = _uuid()
    project_a = _uuid()
    project_b = _uuid()

    db.execute(
        text(
            """
            INSERT INTO project_templates (id, org_id, project_id, active_template_version_id, updated_by)
            VALUES
                (:id1, :org_id, :project_a, NULL, NULL),
                (:id2, :org_id, :project_b, NULL, NULL)
            """
        ),
        {
            "id1": _uuid(),
            "id2": _uuid(),
            "org_id": org_id,
            "project_a": project_a,
            "project_b": project_b,
        },
    )
    return org_id, project_a, project_b


def _create_deliverable(db: Session, org_id: uuid.UUID, project_id: uuid.UUID) -> uuid.UUID:
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
    return deliverable_id


def _create_qc_inspection(
    db: Session, org_id: uuid.UUID, project_id: uuid.UUID, deliverable_id: uuid.UUID
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
            "result": "rejected",
        },
    )
    return qc_id


def test_m6_task_cannot_reference_deliverable_from_other_project(db: Session):
    org_id, project_a, project_b = _create_two_projects_same_org(db)
    deliverable_id = _create_deliverable(db, org_id, project_a)

    # violating insert must be isolated, иначе Session будет в failed-state
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    """
                    INSERT INTO tasks (id, org_id, project_id, deliverable_id, title, kind, status, created_by)
                    VALUES (:id, :org_id, :project_id, :deliverable_id, :title, :kind, :status, :created_by)
                    """
                ),
                {
                    "id": _uuid(),
                    "org_id": org_id,
                    "project_id": project_b,  # ❌ другой project
                    "deliverable_id": deliverable_id,
                    "title": "T",
                    "kind": "production",
                    "status": "available",
                    "created_by": _uuid(),
                },
            )


def test_m6_qc_inspection_must_match_deliverable_project(db: Session):
    org_id, project_a, project_b = _create_two_projects_same_org(db)
    deliverable_id = _create_deliverable(db, org_id, project_a)

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    """
                    INSERT INTO qc_inspections (id, org_id, project_id, deliverable_id, inspector_user_id, result)
                    VALUES (:id, :org_id, :project_id, :deliverable_id, :inspector_user_id, :result)
                    """
                ),
                {
                    "id": _uuid(),
                    "org_id": org_id,
                    "project_id": project_b,  # ❌ другой project
                    "deliverable_id": deliverable_id,
                    "inspector_user_id": _uuid(),
                    "result": "approved",
                },
            )


def test_m6_task_qc_inspection_project_consistency(db: Session):
    org_id, project_a, project_b = _create_two_projects_same_org(db)
    deliverable_id = _create_deliverable(db, org_id, project_a)
    qc_id = _create_qc_inspection(db, org_id, project_a, deliverable_id)

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    """
                    INSERT INTO tasks (id, org_id, project_id, qc_inspection_id, title, kind, status, created_by)
                    VALUES (:id, :org_id, :project_id, :qc_inspection_id, :title, :kind, :status, :created_by)
                    """
                ),
                {
                    "id": _uuid(),
                    "org_id": org_id,
                    "project_id": project_b,  # ❌ другой project
                    "qc_inspection_id": qc_id,
                    "title": "T",
                    "kind": "production",
                    "status": "available",
                    "created_by": _uuid(),
                },
            )


def test_m6_signoff_must_match_deliverable_project(db: Session):
    org_id, project_a, project_b = _create_two_projects_same_org(db)
    deliverable_id = _create_deliverable(db, org_id, project_a)

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    """
                    INSERT INTO deliverable_signoffs (
                        id, org_id, project_id, deliverable_id, signed_off_by, result
                    )
                    VALUES (
                        :id, :org_id, :project_id, :deliverable_id, :signed_off_by, :result
                    )
                    """
                ),
                {
                    "id": _uuid(),
                    "org_id": org_id,
                    "project_id": project_b,  # ❌ другой project
                    "deliverable_id": deliverable_id,
                    "signed_off_by": _uuid(),
                    "result": "approved",
                },
            )
