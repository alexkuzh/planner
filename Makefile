.PHONY: up infra api down ps logs logs-db db psql migrate revision kill-port restart pg-reset postman-run pg-top test-api-contract

# Поднять только инфраструктуру (сейчас это Postgres)
infra:
	docker compose up -d

# Убить процессы, слушающие порт API (по умолчанию 8000)
# Безопасно: скрипт убивает только python/uvicorn на этом порту.
kill-port:
	./scripts/kill_port.sh 8000

# Запустить API локально (в venv)
api: kill-port
	source .venv/bin/activate && python -m uvicorn app.main:app --reload --port 8000

# Всё сразу: Postgres + API
up: kill-port
	docker compose up -d
	source .venv/bin/activate && python -m uvicorn app.main:app --reload --port 8000

# Остановить контейнеры
down:
	docker compose down

# restart
restart: down up

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

pg-reset:
	docker exec -it planner_postgres psql -U planner -d planner -c "SELECT pg_stat_statements_reset();"

postman-run:
	newman run ./postman/collection.json \
	  --env-var base_url=http://127.0.0.1:8000 \
	  --env-var org_id=11111111-1111-1111-1111-111111111111 \
	  --env-var project_id=22222222-2222-2222-2222-222222222222 \
	  --env-var user_id=33333333-3333-3333-3333-333333333333 \
	  --env-var role=lead \
	  -n 200 --delay-request 50


pg-top:
	docker exec -it planner_postgres psql -U planner -d planner -c "\
	SELECT calls, round(total_exec_time::numeric,2) AS total_ms, round(mean_exec_time::numeric,2) AS mean_ms, rows, left(query,220) AS query_short \
	FROM pg_stat_statements \
	ORDER BY total_exec_time DESC \
	LIMIT 15;"

# Contract test battery (API Hardening A1-A5)
# Source of truth: pytest; Postman is for acceptance/debug.
test-api-contract:
	source .venv/bin/activate && pytest -q tests/api_contract
