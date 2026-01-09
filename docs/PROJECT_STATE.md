Ниже — готовый **один файл “бэкап знаний”**. Сохрани как:

`/Users/alex/PycharmProjects/planner/docs/PROJECT_STATE.md`

(если папки `docs` нет — создай)

````md
# Planner — Project State (Knowledge Backup)

Дата: 2026-01-05  
Локальный путь проекта: `/Users/alex/PycharmProjects/planner`

## 1) Что это за проект

Planner — система планирования, исполнения и контроля задач с:
- явной моделью состояний (FSM),
- аудит-логом событий,
- API поверх Postgres,
- возможностью наращивать AI-агентов как помощников ролей (в будущем).

Ключевая идея: **ядро системы детерминированное (DB + правила + FSM), AI — надстройка, а не “истина”.**

---

## 2) Текущий стек (MVP)

- Python (venv, локально)
- FastAPI (Swagger доступен по `/docs`)
- SQLAlchemy 2.x
- Alembic (миграции)
- PostgreSQL в Docker (официальный образ `postgres:16`)
- Управление запуском через `make`

---

## 3) Как запустить (быстро)

### 3.1 Поднять Postgres (Docker)
Из корня проекта:
```bash
make infra
# или: docker compose up -d
````

Проверка:

```bash
docker compose ps
docker logs -f planner_postgres
```

### 3.2 Запустить API (локально в venv)

```bash
make api
# или: source .venv/bin/activate && python -m uvicorn app.main:app --reload --port 8000
```

Проверка:

* Health: `GET http://127.0.0.1:8000/health`
* Swagger UI: `http://127.0.0.1:8000/docs`

### 3.3 Всё сразу

```bash
make up
```

---

## 4) Структура проекта (актуальная)
Проект организован по слоистой архитектуре с явным разделением
домена, сервисов и API.
```text
app/
  main.py                  # FastAPI entrypoint

  core/                    # инфраструктура
    config.py              # настройки приложения
    db.py                  # SQLAlchemy engine / session

  models/                  # доменная модель (SQLAlchemy)
    base.py

    task.py
    task_event.py
    task_transition.py
    task_allocation.py

    deliverable.py
    deliverable_signoff.py
    qc_inspection.py

  schemas/                 # Pydantic-контракты API
    task.py
    task_event.py
    transition.py
    allocation.py

    deliverable.py
    deliverable_actions.py
    deliverable_signoff.py
    deliverable_dashboard.py

    qc_inspection.py

  fsm/                     # правила изменения состояния
    task_fsm.py

  services/                # бизнес-логика (use cases)
    task_transition_service.py
    task_allocation_service.py

  api/                     # HTTP слой (FastAPI routers)
    deps.py
    health.py
    tasks.py
    deliverables.py
    allocations.py

```

---

## 5) Текущая модель данных

### 5.1 `tasks`

Назначение: основная сущность задачи.

Ключевые поля:

* `id` (int, PK)
* `title` (str)
* `status` (enum: `new`, `in_progress`, `done`)
* `created_at`, `updated_at`

### 5.2 `task_events`

Назначение: аудит-лог переходов задачи (события).

Ключевые поля:

* `id` (int, PK)
* `task_id` (FK → tasks.id, CASCADE)
* `action` (str: например `start`, `finish`, `reopen`)
* `from_status` (str)
* `to_status` (str)
* `actor` (str/nullable) — пока не используется, позже привязать к пользователю
* `created_at` (timestamp)

---

## 6) API (основные эндпоинты)

### Health

* `GET /health` → `{"status":"ok"}`

### Tasks (CRUD)

* `POST /tasks` (создать)

* `GET /tasks` (список)

* `GET /tasks/{id}` (получить одну)

* `PATCH /tasks/{id}` (обновить title)
  Примечание: статус напрямую менять нельзя/не рекомендуется — через FSM.

* `DELETE /tasks/{id}` (удалить)

### FSM Transitions

* `POST /tasks/{id}/transition`
  Body: `{"action":"start" | "finish" | "reopen"}`
  Возвращает TaskRead с обновлённым статусом.
  Ошибка при недопустимом действии: `409 Conflict`.

### Audit Log

* `GET /tasks/{id}/events` → список `task_events` по задаче.

---

## 7) FSM (текущие правила)

Файл: `app/fsm/task_fsm.py`

Разрешённые действия:

* `start`: `new` → `in_progress`
* `finish`: `in_progress` → `done`
* `reopen`: `done` → `in_progress`

При попытке выполнить действие из неверного статуса возвращается ошибка с понятным текстом:

* текущее состояние (`current.value`)
* ожидаемое состояние (`expected.value`)

---

## 8) Миграции и типовые проблемы (и как их решали)

* **Alebmic “Target database is not up to date”**
  Причина: БД не на `head` → нужно `alembic upgrade head` перед автогенерацией.

* **Таблица не создавалась при autogenerate (пустая миграция)**
  Причина: модель не попадала в `Base.metadata`.
  Фикс: импортировать модели в `app/models/__init__.py`, чтобы Alembic “видел” таблицы.

* **uvicorn не находится**
  Причина: запуск вне venv.
  Фикс: активировать `.venv` или запускать `python -m uvicorn ...`.

* **порт 8000 занят**
  Фикс: завершить процесс `lsof -i :8000` + `kill -9 PID`, или запускать на другом порту.

---

## 9) Команды (make targets)

Ожидаемые цели:

* `make infra` — поднять Postgres
* `make api` — запустить API локально
* `make up` — infra + api
* `make down` — остановить контейнеры
* `make ps` — статус контейнеров
* `make logs` — логи compose
* `make logs-db` — логи Postgres
* `make psql` — зайти в psql
* `make migrate` — `alembic upgrade head`
* `make revision m="..."` — автогенерация миграции

---

## 10) Куда развивать дальше (ближайшие шаги)

1. **Сервисный слой**

   * вынести логику из роутеров в `app/services/*`
   * единые доменные ошибки

2. **Версионирование/оптимистические блокировки**

   * `expected_row_version` и защита от гонок (в будущем)

3. **Расширение audit log**

   * логировать не только transition, но и create/update/delete
   * добавить `client_event_id` / correlation id (идемпотентность)

4. **Роли и “Supervisor Copilot”**

   * агент как советник постановки задач: генерирует “предложения”, но не меняет данные без подтверждения

5. **Очереди/фоновые задачи (опционально)**

   * Redis + worker (позже, когда появится реальная необходимость)

---

## 11) Быстрый бэкап данных (опционально)

Схема воспроизводится миграциями. Если нужен дамп данных dev-БД:

```bash
docker exec planner_postgres pg_dump -U planner planner > backup.sql
```

Восстановление:

```bash
cat backup.sql | docker exec -i planner_postgres psql -U planner planner
```

```

Если хочешь, я могу:
- добавить в этот файл точные имена файлов (как у тебя сейчас в репо),
- или сделать более “официальный” формат: `ARCHITECTURE.md` + `OPERATIONS.md`, но ты просил именно **один файл**, так что этот вариант оптимальный.
```

## Task classification

### task.kind
Domain classification of task:
- production
- maintenance
- admin
- other

This field describes **what domain the task belongs to**.
It is NOT used to distinguish fixes.

### task.work_kind
Type of work:
- work — normal planned work
- fix — corrective / rework task

This field is orthogonal to `task.kind`.

### Fix-task definition
A fix-task is a regular Task with:
- work_kind = fix
- fix_source != NULL
- fix_severity != NULL

Fix-tasks may be created by:
- QC reject
- worker initiative
- supervisor request

Fix-tasks are used for:
- QC rework
- proactive defect fixing
- bonus and quality analytics
