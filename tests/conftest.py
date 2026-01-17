# tests/conftest.py
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker as _sessionmaker

from app.core.config import settings

# -----------------------------------------------------------------------------
# IMPORTANT: ensure all ORM tables are registered in metadata before first flush
# (prevents NoReferencedTableError for FK targets like qc_inspections)
# -----------------------------------------------------------------------------
# If you have a "models/__init__.py" that imports all models, you can replace
# these explicit imports with:  import app.models  # noqa
import app.models.task  # noqa: F401
import app.models.qc_inspection  # noqa: F401
import app.models.deliverable  # noqa: F401
import app.models.task_allocation  # noqa: F401
import app.models.deliverable_signoff  # noqa: F401
import app.models.task_event  # noqa: F401
import app.models.task_transition  # noqa: F401


def _test_database_url() -> str:
    """
    Take settings.database_url and change ONLY database name to planner_test.
    IMPORTANT: must not use str(url) because SQLAlchemy masks password as "***".
    """
    url = make_url(settings.database_url).set(database="planner_test")
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(_test_database_url(), future=True)
    try:
        yield eng
    finally:
        eng.dispose()



@pytest.fixture()
def db(engine):
    """
    Isolation pattern (SQLAlchemy 2.x compatible):
      - connection per test
      - begin OUTER transaction immediately (before any execute/autobegin)
      - session bound to this connection
      - session.begin_nested() creates SAVEPOINT
      - after_transaction_end => restart SAVEPOINT

    Teardown:
      - remove listener first
      - close session
      - rollback ONLY outer transaction
      - close connection
    """
    connection = engine.connect()

    # Begin outer transaction BEFORE any execute() (execute triggers autobegin)
    outer = connection.begin()

    # Sanity check: we really talk to planner_test
    current_db = connection.execute(text("select current_database()")).scalar_one()
    assert current_db == "planner_test"

    Session = _sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    session = Session()

    # Start nested transaction (SAVEPOINT) for test isolation
    session.begin_nested()

    def _restart_savepoint(sess, trans):
        # When SAVEPOINT ends (commit/rollback), open a new one automatically
        if trans.nested and not sess.in_nested_transaction():
            sess.begin_nested()

    event.listen(session, "after_transaction_end", _restart_savepoint)

    try:
        yield session
    finally:
        # IMPORTANT: remove listener before closing/rolling back
        event.remove(session, "after_transaction_end", _restart_savepoint)

        # Close session first (it may be in failed state after an exception)
        session.close()

        # Rollback only the OUTER transaction if still active
        if outer.is_active:
            outer.rollback()

        connection.close()
