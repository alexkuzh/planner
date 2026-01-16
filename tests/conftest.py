import os
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# --- TEST DATABASE URL ---
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://planner:planner@localhost:5432/planner_test",
)

# ВАЖНО: якорим settings приложения (если где-то используются)
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("DATABASE_DSN", TEST_DATABASE_URL)
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", TEST_DATABASE_URL)

# ⚠️ ОБЯЗАТЕЛЬНО: регистрируем таблицу qc_inspections в metadata
import app.models.qc_inspection  # noqa: F401
import app.models


# --- ENGINE ---
@pytest.fixture(scope="session")
def engine():
    return create_engine(
        TEST_DATABASE_URL,
        isolation_level="READ COMMITTED",
        pool_pre_ping=True,
    )


# --- DB SESSION (nested transaction per test) ---
@pytest.fixture()
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()  # outer transaction

    SessionLocal = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
    )
    session = SessionLocal()

    # SAVEPOINT — ключевая часть
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
