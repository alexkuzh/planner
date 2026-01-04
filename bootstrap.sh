#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"

mkdir -p app/api app/core app/models alembic/versions

# ---------------------------
# Python package markers
# ---------------------------
touch app/__init__.py
touch app/api/__init__.py
touch app/core/__init__.py
touch app/models/__init__.py

# ---------------------------
# app/main.py
# ---------------------------
if [ ! -f app/main.py ]; then
cat > app/main.py <<'PY'
from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(health_router, tags=["health"])
PY
fi

# ---------------------------
# app/api/health.py
# ---------------------------
if [ ! -f app/api/health.py ]; then
cat > app/api/health.py <<'PY'
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}
PY
fi

# ---------------------------
# app/core/config.py
# ---------------------------
if [ ! -f app/core/config.py ]; then
cat > app/core/config.py <<'PY'
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "planner"
    env: str = "local"
    debug: bool = True

    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "planner"
    db_user: str = "planner"
    db_password: str = "planner"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
PY
fi

# ---------------------------
# app/core/db.py
# ---------------------------
if [ ! -f app/core/db.py ]; then
cat > app/core/db.py <<'PY'
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
PY
fi

# ---------------------------
# app/models/base.py
# ---------------------------
if [ ! -f app/models/base.py ]; then
cat > app/models/base.py <<'PY'
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
PY
fi

# ---------------------------
# app/models/task.py (пример модели)
# ---------------------------
if [ ! -f app/models/task.py ]; then
cat > app/models/task.py <<'PY'
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaskStatus(str, enum.Enum):
    new = "new"
    in_progress = "in_progress"
    done = "done"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)

    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.new,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
PY
fi

# ---------------------------
# app/models/__init__.py
# ---------------------------
# Если файл пустой/новый — заполним минимальным экспортом.
# Если уже есть и не пустой — не трогаем.
if [ ! -s app/models/__init__.py ]; then
cat > app/models/__init__.py <<'PY'
from app.models.base import Base
from app.models.task import Task

__all__ = ["Base", "Task"]
PY
fi

# ---------------------------
# .env.example
# ---------------------------
if [ ! -f .env.example ]; then
cat > .env.example <<'ENV'
APP_NAME=planner
ENV=local
DEBUG=true

DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=planner
DB_USER=planner
DB_PASSWORD=planner
ENV
fi

# ---------------------------
# docker-compose.yml
# ---------------------------
if [ ! -f docker-compose.yml ]; then
cat > docker-compose.yml <<'YAML'
services:
  postgres:
    image: postgres:16
    container_name: planner_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: planner
      POSTGRES_USER: planner
      POSTGRES_PASSWORD: planner
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U planner -d planner"]
      interval: 5s
      timeout: 5s
      retries: 20

volumes:
  postgres_data:
YAML
fi

# ---------------------------
# alembic.ini
# ---------------------------
if [ ! -f alembic.ini ]; then
cat > alembic.ini <<'INI'
[alembic]
script_location = alembic
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = INFO
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
INI
fi

# ---------------------------
# alembic/env.py
# ---------------------------
if [ ! -f alembic/env.py ]; then
cat > alembic/env.py <<'PY'
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models import Base  # важно: metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
PY
fi

# ---------------------------
# alembic/script.py.mako (минимальный)
# ---------------------------
if [ ! -f alembic/script.py.mako ]; then
cat > alembic/script.py.mako <<'MAKO'
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
MAKO
fi

touch alembic/versions/.gitkeep

# ---------------------------
# .gitignore (минимальный)
# ---------------------------
if [ ! -f .gitignore ]; then
cat > .gitignore <<'GIT'
.venv/
__pycache__/
*.pyc
.env
.idea/
.pytest_cache/
ruff_cache/
.DS_Store
GIT
fi

echo "✅ Bootstrap complete in: $ROOT"
echo "Next:"
echo "  1) cp .env.example .env"
echo "  2) docker compose up -d"
echo "  3) source .venv/bin/activate"
echo "  4) pip install -U pip && pip install -e '.[dev]'   (если еще не ставил)"
echo "  5) alembic revision --autogenerate -m 'init' && alembic upgrade head"
