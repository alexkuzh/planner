from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.task import Task


def _now_utc():
    return datetime.now(timezone.utc)


def _make_task(
    db: Session,
    org_id,
    project_id,
    *,
    status: str,
    row_version: int = 1,
    assigned_to=None,
    assigned_at=None,
) -> Task:
    """
    Create a task that satisfies DB invariants.

    DB CHECK ck_tasks_assigned_fields_consistent requires:
      - for statuses like 'assigned' / 'in_progress': assigned_to AND assigned_at must be NOT NULL
    """
    t = Task(
        org_id=org_id,
        project_id=project_id,
        created_by=uuid4(),
        title="RBAC contract task",
        description="",
        status=status,
        row_version=row_version,
        priority=0,
        # keep defaults for kind/work_kind/etc. via model defaults
        assigned_to=assigned_to,
        assigned_at=assigned_at,
    )
    db.add(t)
    db.flush()
    return t


def _hdr(role: str, actor_id) -> dict[str, str]:
    return {"X-Role": role, "X-Actor-User-Id": str(actor_id)}


def test_rbac_assign_system_forbidden(client, api_db, org_and_project_id):
    """system MUST be forbidden for task.assign -> 403"""
    org_id, project_id = org_and_project_id
    task = _make_task(api_db, org_id, project_id, status="available", row_version=1)
    api_db.commit()

    actor_id = uuid4()
    body = {
        "org_id": str(org_id),
        "actor_user_id": str(actor_id),
        "action": "assign",
        "expected_row_version": 1,
        "client_event_id": str(uuid4()),
        "payload": {"assign_to": str(actor_id)},
    }

    r = client.post(
        f"/tasks/{task.id}/transitions",
        json=body,
        headers=_hdr("system", actor_id),
    )
    assert r.status_code == 403, r.text


def test_rbac_assign_executor_forbidden(client, api_db, org_and_project_id):
    """executor MUST be forbidden for task.assign -> 403"""
    org_id, project_id = org_and_project_id
    task = _make_task(api_db, org_id, project_id, status="available", row_version=1)
    api_db.commit()

    actor_id = uuid4()
    body = {
        "org_id": str(org_id),
        "actor_user_id": str(actor_id),
        "action": "assign",
        "expected_row_version": 1,
        "client_event_id": str(uuid4()),
        "payload": {"assign_to": str(actor_id)},
    }

    r = client.post(
        f"/tasks/{task.id}/transitions",
        json=body,
        headers=_hdr("executor", actor_id),
    )
    assert r.status_code == 403, r.text


def test_rbac_assign_lead_allowed(client, api_db, org_and_project_id):
    """lead MUST be allowed for task.assign -> 200"""
    org_id, project_id = org_and_project_id
    task = _make_task(api_db, org_id, project_id, status="available", row_version=1)
    api_db.commit()

    actor_id = uuid4()
    body = {
        "org_id": str(org_id),
        "actor_user_id": str(actor_id),
        "action": "assign",
        "expected_row_version": 1,
        "client_event_id": str(uuid4()),
        "payload": {"assign_to": str(actor_id)},
    }

    r = client.post(
        f"/tasks/{task.id}/transitions",
        json=body,
        headers=_hdr("lead", actor_id),
    )
    assert r.status_code == 200, r.text


def test_rbac_start_executor_allowed(client, api_db, org_and_project_id):
    """
    executor MUST be allowed for task.start -> 200

    To avoid FSM rejection AND satisfy DB invariants:
      - task must be 'assigned'
      - assigned_to + assigned_at must be set
      - actor_user_id == assigned_to
    """
    org_id, project_id = org_and_project_id
    assignee_id = uuid4()

    task = _make_task(
        api_db,
        org_id,
        project_id,
        status="assigned",
        row_version=1,
        assigned_to=assignee_id,
        assigned_at=_now_utc(),
    )
    api_db.commit()

    actor_id = assignee_id
    body = {
        "org_id": str(org_id),
        "actor_user_id": str(actor_id),
        "action": "start",
        "expected_row_version": 1,
        "client_event_id": str(uuid4()),
        "payload": {},
    }

    r = client.post(
        f"/tasks/{task.id}/transitions",
        json=body,
        headers=_hdr("executor", actor_id),
    )
    assert r.status_code == 200, r.text


def test_rbac_submit_executor_allowed(client, api_db, org_and_project_id):
    """
    executor MUST be allowed for task.submit -> 200

    To avoid FSM rejection AND satisfy DB invariants:
      - task must be 'in_progress'
      - assigned_to + assigned_at must be set
      - actor_user_id == assigned_to
    """
    org_id, project_id = org_and_project_id
    assignee_id = uuid4()

    task = _make_task(
        api_db,
        org_id,
        project_id,
        status="in_progress",
        row_version=1,
        assigned_to=assignee_id,
        assigned_at=_now_utc(),
    )
    api_db.commit()

    actor_id = assignee_id
    body = {
        "org_id": str(org_id),
        "actor_user_id": str(actor_id),
        "action": "submit",
        "expected_row_version": 1,
        "client_event_id": str(uuid4()),
        "payload": {},
    }

    r = client.post(
        f"/tasks/{task.id}/transitions",
        json=body,
        headers=_hdr("executor", actor_id),
    )
    assert r.status_code == 200, r.text
