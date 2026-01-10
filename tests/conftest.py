import os
import pytest
# tests/conftest.py
# ВАЖНО: импортируем модели, чтобы все таблицы попали в Base.metadata
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.models.qc_inspection  # noqa: F401


TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://planner:planner@localhost:5432/planner_test",
)

@pytest.fixture(scope="session")
def engine():
    return create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

@pytest.fixture(scope="session")
def SessionLocal(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)

@pytest.fixture()
def db(SessionLocal):
    session = SessionLocal()
    try:
        yield session
    finally:
        # безопасно даже если транзакция уже откатилась внутри теста/сервиса
        try:
            session.rollback()
        finally:
            session.close()
