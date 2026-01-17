from uuid import uuid4


def test_allocations_batch_rejects_extra_fields(client, org_and_project_id, headers):
    """
    A1: allocations batch must reject extra fields with 422.
    """
    org_id, project_id = org_and_project_id

    body = {
        "org_id": str(org_id),
        "project_id": str(project_id),
        "items": [
            {
                "task_id": str(uuid4()),
                "user_id": str(uuid4()),
                "unexpected_field": "boom",  # ❌ extra
            }
        ],
    }

    r = client.post("/allocations/batch", json=body, headers=headers)
    assert r.status_code == 422, r.text


def test_allocations_batch_rejects_wrong_type(client, org_and_project_id, headers):
    """
    A1: wrong UUID types must be rejected deterministically.
    """
    org_id, project_id = org_and_project_id

    body = {
        "org_id": str(org_id),
        "project_id": str(project_id),
        "items": [
            {
                "task_id": "not-a-uuid",  # ❌ wrong
                "user_id": str(uuid4()),
            }
        ],
    }

    r = client.post("/allocations/batch", json=body, headers=headers)
    assert r.status_code == 422, r.text
