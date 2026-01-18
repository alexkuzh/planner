from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "openapi_v2_snapshot.json"


def _normalize(schema: dict) -> dict:
    def sort_obj(obj):
        if isinstance(obj, dict):
            return {k: sort_obj(obj[k]) for k in sorted(obj)}
        if isinstance(obj, list):
            return [sort_obj(x) for x in obj]
        return obj

    schema = dict(schema)
    schema.pop("servers", None)
    return sort_obj(schema)


def test_openapi_v2_snapshot_is_stable():
    assert SNAPSHOT_PATH.exists(), (
        "openapi_v2_snapshot.json not found. "
        "Run: python scripts/openapi_snapshot.py --write"
    )

    client = TestClient(app)
    resp = client.get("/openapi.json")
    resp.raise_for_status()

    current = _normalize(resp.json())
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert current == expected, (
        "OpenAPI snapshot mismatch.\n"
        "If this change is intentional, update snapshot with:\n"
        "  python scripts/openapi_snapshot.py --write"
    )
