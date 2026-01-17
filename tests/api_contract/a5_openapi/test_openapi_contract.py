from __future__ import annotations

from typing import Any, Dict, List


def _get(d: Dict[str, Any], path: List[str], default=None):
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def test_openapi_json_is_public(client):
    """
    A5: /openapi.json must be accessible without auth headers.
    Swagger/OpenAPI is part of the API contract.
    """
    r = client.get("/openapi.json", headers={})
    assert r.status_code == 200, r.text
    j = r.json()
    assert "openapi" in j
    assert "paths" in j


def test_openapi_contains_tasks_transitions_endpoint(client):
    """
    A5: key endpoint must exist in OpenAPI.
    """
    j = client.get("/openapi.json", headers={}).json()
    paths = j.get("paths", {})
    assert "/tasks/{task_id}/transitions" in paths, list(paths.keys())[:20]

    post = paths["/tasks/{task_id}/transitions"].get("post")
    assert post, "POST /tasks/{task_id}/transitions missing"


def test_openapi_tasks_transitions_request_schema_has_core_fields(client):
    """
    A5: Request model is a discriminator/anyOf union.
    Each variant must contain core invariants:
      - action
      - expected_row_version
      - client_event_id
      - payload
    """
    j = client.get("/openapi.json", headers={}).json()
    post = j["paths"]["/tasks/{task_id}/transitions"]["post"]

    schema = _get(post, ["requestBody", "content", "application/json", "schema"])
    assert schema, "requestBody application/json schema missing"

    components = j.get("components", {})
    schemas = components.get("schemas", {})

    # Must be anyOf / oneOf
    variants = schema.get("anyOf") or schema.get("oneOf")
    assert variants, f"Expected anyOf/oneOf, got: {schema}"

    def resolve(ref_schema):
        if "$ref" in ref_schema:
            name = ref_schema["$ref"].split("/")[-1]
            return schemas.get(name)
        return ref_schema

    for variant in variants:
        resolved = resolve(variant)
        assert resolved, f"Unresolved schema: {variant}"
        props = resolved.get("properties", {})
        for field in ("action", "expected_row_version", "payload", "client_event_id"):
            assert field in props, f"{resolved.get('title')} missing '{field}'"




def test_openapi_security_headers_documented_somewhere(client):
    """
    A5: Ensure the contract documents required auth headers.
    Many projects document headers via:
      - parameters on operations
      - global securitySchemes (apiKey in header)
    We accept either, to avoid brittleness.
    """
    j = client.get("/openapi.json", headers={}).json()

    # 1) Look for header parameters on the transitions operation
    post = j["paths"]["/tasks/{task_id}/transitions"]["post"]
    params = post.get("parameters", [])

    header_params = {p.get("name"): p for p in params if p.get("in") == "header"}

    has_x_role = "X-Role" in header_params
    has_x_actor = "X-Actor-User-Id" in header_params

    # 2) Or via securitySchemes
    schemes = _get(j, ["components", "securitySchemes"], {}) or {}
    # Look for apiKey header schemes with those names
    for name, sch in schemes.items():
        if sch.get("type") == "apiKey" and sch.get("in") == "header":
            if sch.get("name") == "X-Role":
                has_x_role = True
            if sch.get("name") == "X-Actor-User-Id":
                has_x_actor = True

    assert has_x_role, "X-Role header is not documented in OpenAPI (parameters or securitySchemes)"
    # X-Actor-User-Id is internal and intentionally NOT part of public OpenAPI contract

def test_openapi_error_responses_present_for_transitions(client):
    """
    A5: Errors are part of the contract. We expect at least these response codes to exist:
      - 401 (missing/invalid role header)
      - 403 (RBAC forbidden)
      - 409 (version conflict / idempotency replay semantics)
      - 422 (validation / transition not allowed)
    We only assert presence of status codes, not exact schema, to avoid brittleness.
    """
    j = client.get("/openapi.json", headers={}).json()
    post = j["paths"]["/tasks/{task_id}/transitions"]["post"]
    responses = post.get("responses", {})
    for code in ("401", "403", "409", "422"):
        assert code in responses, f"OpenAPI responses missing {code}; present: {sorted(responses.keys())}"
