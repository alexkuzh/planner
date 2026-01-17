import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _t0() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _assert_m8_constraints_present(db: Session) -> None:
    need = {"ck_tasks_created_le_assigned"}

    rows = db.execute(
        text(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'public.tasks'::regclass
              AND contype = 'c'
            """
        )
    ).all()
    present = {r[0] for r in rows}
    missing = sorted(need - present)
    assert not missing, (
        "M8 constraints are missing in DB (migration not applied?): "
        + ", ".join(missing)
    )


def _setup_project(db: Session) -> tuple[uuid.UUID, uuid.UUID]:
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
    return org_id, project_id


def _insert_task_assigned(
    db: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    created_at: datetime,
    updated_at: datetime,
    assigned_at: datetime,
) -> uuid.UUID:
    task_id = _uuid()
    db.execute(
        text(
            """
            INSERT INTO tasks (
                id, org_id, project_id,
                title, kind, status, created_by,
                assigned_to, assigned_at,
                created_at, updated_at
            )
            VALUES (
                :id, :org_id, :project_id,
                :title, :kind, :status, :created_by,
                :assigned_to, :assigned_at,
                :created_at, :updated_at
            )
            """
        ),
        {
            "id": task_id,
            "org_id": org_id,
            "project_id": project_id,
            "title": "Task",
            "kind": "production",
            "status": "assigned",
            "created_by": _uuid(),
            "assigned_to": _uuid(),
            "assigned_at": assigned_at,
            "created_at": created_at,
            "updated_at": updated_at,
        },
    )
    return task_id


def test_m8_assigned_at_cannot_be_before_created_at(db: Session):
    _assert_m8_constraints_present(db)
    org_id, project_id = _setup_project(db)

    base = _t0()
    created_at = base
    updated_at = base + timedelta(minutes=10)
    assigned_at = base - timedelta(minutes=1)  # ❌ раньше created_at

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _insert_task_assigned(
                db,
                org_id=org_id,
                project_id=project_id,
                created_at=created_at,
                updated_at=updated_at,
                assigned_at=assigned_at,
            )
            db.flush()


def test_m8_valid_assigned_at_at_or_after_created_at(db: Session):
    _assert_m8_constraints_present(db)
    org_id, project_id = _setup_project(db)

    base = _t0()
    created_at = base
    assigned_at = base + timedelta(minutes=1)
    updated_at = base  # не важно для M8.1.A

    _insert_task_assigned(
        db,
        org_id=org_id,
        project_id=project_id,
        created_at=created_at,
        updated_at=updated_at,
        assigned_at=assigned_at,
    )
    db.flush()
