import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker as _sessionmaker

from app.core.config import settings


@pytest.fixture(scope="session")
def engine():
    # ВАЖНО: в проекте это свойство называется database_url
    return create_engine(settings.database_url)


@pytest.fixture(scope="session")
def sessionmaker(engine):
    return _sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


@pytest.fixture()
def db(engine):
    """
    Isolation pattern:
      - connection.begin() outer transaction per test
      - session.begin_nested() SAVEPOINT, so IntegrityError doesn't poison whole test
    Teardown:
      - rollback outer transaction (always safe, no 'deassociated' warnings)
    """
    connection = engine.connect()
    outer = connection.begin()

    Session = _sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = Session()

    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not sess.in_nested_transaction():
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        if outer.is_active:
            outer.rollback()
        connection.close()
