.PHONY: up infra api down ps logs logs-db db psql migrate revision

# Поднять только инфраструктуру (сейчас это Postgres)
infra:
	docker compose up -d

# Запустить API локально (в venv)
api:
	source .venv/bin/activate && python -m uvicorn app.main:app --reload --port 8000

# Всё сразу: Postgres + API
up:
	docker compose up -d
	source .venv/bin/activate && python -m uvicorn app.main:app --reload --port 8000

# Остановить контейнеры
down:
	docker compose down

# Показать статус контейнеров
ps:
	docker compose ps

# Логи всех сервисов
logs:
	docker compose logs -f

# Логи Postgres
logs-db:
	docker logs -f planner_postgres

# Поднять/перезапустить только Postgres
db:
	docker compose up -d postgres

# Подключиться к Postgres внутри контейнера
psql:
	docker exec -it planner_postgres psql -U planner -d planner

# Применить миграции Alembic (локально в venv)
migrate:
	source .venv/bin/activate && alembic upgrade head

# Создать ревизию Alembic (пример: make revision m="add audit log")
revision:
	source .venv/bin/activate && alembic revision --autogenerate -m "$(m)"
