from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = ROOT / "openapi_v2_snapshot.json"


def _normalize_openapi(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Делает OpenAPI JSON детерминированным:
    - сортирует dict'ы
    - убирает runtime-шум (servers, timestamps и т.п.)
    """

    def sort_obj(obj):
        if isinstance(obj, dict):
            return {k: sort_obj(obj[k]) for k in sorted(obj)}
        if isinstance(obj, list):
            return [sort_obj(x) for x in obj]
        return obj

    schema = dict(schema)  # shallow copy

    # FastAPI иногда добавляет servers динамически
    schema.pop("servers", None)

    return sort_obj(schema)


def generate_openapi() -> dict[str, Any]:
    client = TestClient(app)
    resp = client.get("/openapi.json")
    resp.raise_for_status()
    return _normalize_openapi(resp.json())


def write_snapshot() -> None:
    schema = generate_openapi()
    SNAPSHOT_PATH.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] OpenAPI snapshot written to {SNAPSHOT_PATH}")


def check_snapshot() -> None:
    if not SNAPSHOT_PATH.exists():
        print(
            f"[ERROR] Snapshot not found: {SNAPSHOT_PATH}\n"
            f"Run: python scripts/openapi_snapshot.py --write",
            file=sys.stderr,
        )
        sys.exit(1)

    current = generate_openapi()
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    if current != expected:
        print("[ERROR] OpenAPI snapshot mismatch!", file=sys.stderr)
        print(
            "If this change is intentional, update snapshot with:\n"
            "  python scripts/openapi_snapshot.py --write",
            file=sys.stderr,
        )
        sys.exit(1)

    print("[OK] OpenAPI snapshot matches")


def main() -> None:
    parser = argparse.ArgumentParser("OpenAPI v2 snapshot tool")
    parser.add_argument("--write", action="store_true", help="Write snapshot")
    parser.add_argument("--check", action="store_true", help="Check snapshot")
    args = parser.parse_args()

    if args.write == args.check:
        parser.error("Specify exactly one of --write or --check")

    if args.write:
        write_snapshot()
    else:
        check_snapshot()


if __name__ == "__main__":
    main()
