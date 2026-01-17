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
    t = Task(
        org_id=org_id,
        project_id=project_id,
        created_by=uuid4(),
        title="A4 contract task",
        description="",
        status=status,
        row_version=row_version,
        priority=0,
        assigned_to=assigned_to,
        assigned_at=assigned_at,
    )
    db.add(t)
    db.flush()
    return t


def _hdr(role: str, actor_id) -> dict[str, str]:
    return {"X-Role": role, "X-Actor-User-Id": str(actor_id)}


def test_out_of_order_start_from_available_is_422(client, api_db, org_and_project_id):
    """
    A4: start cannot be called from 'available' (must be assigned).
    Expect deterministic 422 (TransitionNotAllowed / validation).
    """
    org_id, project_id = org_and_project_id
    task = _make_task(api_db, org_id, project_id, status="available", row_version=1)
    api_db.commit()

    actor_id = uuid4()
    body = {
        "org_id": str(org_id),
        "actor_user_id": str(actor_id),
        "action": "start",
        "expected_row_version": 1,
        "client_event_id": str(uuid4()),
        "payload": {},
    }

    # RBAC: start allowed for executor/lead. Use executor.
    r = client.post(
        f"/tasks/{task.id}/transitions",
        json=body,
        headers=_hdr("executor", actor_id),
    )
    assert r.status_code == 422, r.text


def test_out_of_order_submit_from_assigned_is_422(client, api_db, org_and_project_id):
    """
    A4: submit cannot be called from 'assigned' (must be in_progress).
    Expect deterministic 422.
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
    assert r.status_code == 422, r.text


def test_version_conflict_wrong_expected_row_version_is_409(client, api_db, org_and_project_id):
    """
    A4: wrong expected_row_version must return 409 VersionConflict deterministically.
    """
    org_id, project_id = org_and_project_id
    task = _make_task(api_db, org_id, project_id, status="available", row_version=1)
    api_db.commit()

    actor_id = uuid4()
    body = {
        "org_id": str(org_id),
        "actor_user_id": str(actor_id),
        "action": "assign",
        "expected_row_version": 999,  # wrong
        "client_event_id": str(uuid4()),
        "payload": {"assign_to": str(actor_id)},
    }

    r = client.post(
        f"/tasks/{task.id}/transitions",
        json=body,
        headers=_hdr("lead", actor_id),
    )
    assert r.status_code == 409, r.text


def test_race_two_assign_same_expected_row_version_one_wins_other_409(client, api_db, org_and_project_id):
    """
    A4: simulate HTTP race (sequentially) with same expected_row_version.
    First assign should succeed (200), second should deterministically 409.
    """
    org_id, project_id = org_and_project_id
    task = _make_task(api_db, org_id, project_id, status="available", row_version=1)
    api_db.commit()

    lead_id = uuid4()
    headers_lead = _hdr("lead", lead_id)

    body = {
        "org_id": str(org_id),
        "actor_user_id": str(lead_id),
        "action": "assign",
        "expected_row_version": 1,
        "client_event_id": str(uuid4()),
        "payload": {"assign_to": str(uuid4())},
    }

    r1 = client.post(f"/tasks/{task.id}/transitions", json=body, headers=headers_lead)
    assert r1.status_code == 200, r1.text

    # second request still claims expected_row_version=1 -> must conflict
    body2 = {**body, "client_event_id": str(uuid4())}
    r2 = client.post(f"/tasks/{task.id}/transitions", json=body2, headers=headers_lead)
    assert r2.status_code == 409, r2.text


def test_idempotency_race_same_client_event_id_returns_same_result(client, api_db, org_and_project_id):
    """
    A4 + A2 semantics (Variant A):
      Two identical requests with same client_event_id return same response (200 both),
      second is replay-safe.
    """
    org_id, project_id = org_and_project_id
    task = _make_task(api_db, org_id, project_id, status="available", row_version=1)
    api_db.commit()

    lead_id = uuid4()
    event_id = uuid4()

    body = {
        "org_id": str(org_id),
        "actor_user_id": str(lead_id),
        "action": "assign",
        "expected_row_version": 1,
        "client_event_id": str(event_id),
        "payload": {"assign_to": str(uuid4())},
    }

    headers_lead = _hdr("lead", lead_id)

    r1 = client.post(f"/tasks/{task.id}/transitions", json=body, headers=headers_lead)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()

    r2 = client.post(f"/tasks/{task.id}/transitions", json=body, headers=headers_lead)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()

    assert j2 == j1
