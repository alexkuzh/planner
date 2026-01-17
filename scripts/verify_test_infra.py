# scripts/verify_test_infra.py
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings


def die(msg: str) -> None:
    print(f"[verify-test-infra] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    # --- build test DB url exactly like tests do ---
    url = make_url(settings.database_url).set(database="planner_test")
    db_url = url.render_as_string(hide_password=False)

    engine = create_engine(db_url, future=True)

    with engine.connect() as conn:
        # 1) ensure correct database
        current_db = conn.execute(
            text("select current_database()")
        ).scalar_one()
        if current_db != "planner_test":
            die(f"connected to '{current_db}', expected 'planner_test'")

        print("[ok] connected to planner_test")

        # 2) alembic version must exist
        try:
            version = conn.execute(
                text("select version_num from alembic_version")
            ).scalar_one()
        except Exception as e:  # pragma: no cover
            die(f"alembic_version table missing: {e}")

        print(f"[ok] alembic_version = {version}")

        # 3) required tables
        required_tables = {
            "tasks",
            "task_allocations",
            "project_templates",
            "qc_inspections",
        }

        rows = conn.execute(
            text(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                """
            )
        ).scalars().all()

        present = set(rows)
        missing = required_tables - present
        if missing:
            die(f"missing tables: {sorted(missing)}")

        print("[ok] required tables present")

        # 4) required FK on task_allocations
        fk = conn.execute(
            text(
                """
                select constraint_name
                from information_schema.table_constraints
                where table_name = 'task_allocations'
                  and constraint_type = 'FOREIGN KEY'
                """
            )
        ).scalars().all()

        if "fk_task_allocations_task_org" not in fk:
            die("missing FK fk_task_allocations_task_org on task_allocations")

        print("[ok] fk_task_allocations_task_org present")

        # 5) sanity columns for task_allocations
        cols = conn.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_name = 'task_allocations'
                """
            )
        ).scalars().all()

        expected_cols = {
            "id",
            "org_id",
            "task_id",
            "user_id",
            "role",
            "created_at",
        }

        missing_cols = expected_cols - set(cols)
        if missing_cols:
            die(f"task_allocations missing columns: {sorted(missing_cols)}")

        print("[ok] task_allocations columns sane")

    engine.dispose()
    print("[verify-test-infra] ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
