from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text


def _db_name(dsn: str) -> str:
    u = urlparse(dsn)
    return (u.path or "").lstrip("/") or "<unknown>"


def _all(engine, sql: str) -> list[str]:
    with engine.connect() as c:
        return [r[0] for r in c.execute(text(sql)).all()]


@pytest.mark.e2e_gate
def test_test_db_schema_has_required_tables():
    db_test = os.getenv("DB_TEST")
    assert db_test, "DB_TEST env var is required (SQLAlchemy DSN to planner_test)."

    eng = create_engine(db_test)

    required = {
        "alembic_version",
        "project_templates",
        "project_template_versions",
        "project_template_nodes",
        "project_template_edges",
        "deliverables",
        "tasks",
        "task_events",
        "task_dependencies",
    }

    existing = set(_all(eng, "SELECT tablename FROM pg_tables WHERE schemaname='public'"))
    missing = sorted(required - existing)

    assert not missing, (
        f"Missing tables in test DB {_db_name(db_test)}: {missing}. "
        "Run migrations for planner_test (alembic -c alembic_test.ini upgrade head)."
    )
