# ARCHITECTURE.md

## 0. Цель проекта

`planner` — внутренний сервис управления производственным процессом по изделиям (**deliverables**) через дерево задач (**tasks**) с зависимостями, FSM-переходами и QC-контуром.

Ключевая идея: **изделие (deliverable) — контейнер работ**, а задачи — “DNA” процесса, разворачиваемое из шаблона проекта (bootstrap). Исправления (fix) — отдельный тип работы, создаваемый строго через сервис и проверяемый инвариантами.

---

## 1. Доменная модель

### 1.1 Deliverable (изделие)
**Deliverable** — единица производства: тип + серийник + статус.

Основные статусы (MVP):
- `open`
- `submitted_to_qc`
- `qc_approved`
- `qc_rejected`

Поток:
1) `open` → (production sign-off approved) → `submitted_to_qc`
2) QC решение:
   - approve → `qc_approved`
   - reject → `qc_rejected` + создаётся fix-task (через `TaskFixService`) + пишется `QcInspection`

---

### 1.2 Task (задача)
**Task** — конкретная работа в рамках проекта и (обычно) изделия.

Важные поля:
- `status` (FSM-статус) — **строка в БД**, управляется переходами
- `kind` — доменная классификация: `production / maintenance / admin / other` (не про fix)
- `work_kind` — тип работы: `work | fix` (**ортогонально** `kind`)
- WBS/иерархия: `parent_task_id`
- связи исправлений: `origin_task_id`, `qc_inspection_id`
- `row_version` — optimistic lock

---

### 1.3 Task Dependencies (зависимости)
`task_dependencies` задаёт граф: `predecessor -> successor`.
Используется для вычисления blockers.

---

### 1.4 Task Transition (переходы)
`TaskTransition` — журнал переходов FSM (timeline):
- `action`, `from_status`, `to_status`
- `payload`
- `client_event_id` для идемпотентности
- уникальность: `(org_id, client_event_id)` (MVP)

---

### 1.5 QC контур
**QcInspection** фиксирует результат проверки изделия:
- `approved | rejected`
- `notes` обязательно при reject (инвариант в schema)

При reject:
- создаётся fix-task через `TaskFixService.create_qc_reject_fix(...)`
- определяется `responsible_user_id` как последний approved signoff

---

## 2. Инварианты (обязательные правила)

### I1. Мультитенантность
Все сущности относятся к `org_id`. Все запросы и фильтры должны учитывать `org_id` (MVP: часть параметров пока в body/query).

---

### I2. Optimistic Lock
Любой endpoint, меняющий `Task`, должен проверять:
- `expected_row_version == task.row_version`

Нарушение → `409 Conflict`.

Реализация: `apply_task_transition(...)` в `task_transition_service.py`.

---

### I3. Idempotency
Если передан `client_event_id`, повторный запрос должен вернуть тот же эффект (или результат), без повторного изменения.

Реализация:
- проверка `TaskTransition` по `(org_id, client_event_id)`
- уникальный индекс БД защищает от гонок

---

### I4. Fix-task создаётся только через TaskFixService
**Запрещено** напрямую делать `Task(...)` для fix в API/других сервисах.

Единственная точка создания fix:
- `app/services/task_fix_service.py`

---

### I5. Инварианты fix-task
Если `work_kind == fix`:
- `fix_source` обязателен
- `fix_severity` обязателен
- должен быть контекст: `origin_task_id` или `qc_inspection_id` или `deliverable_id`
- `qc_reject` требует `qc_inspection_id`
- `worker_initiative` требует `origin_task_id` или `deliverable_id`

Реализация: `app/services/fix_invariants.py::validate_fix_task`

---

### I6. “Страховка” от случайного создания fix через обычные потоки
Обычные способы создания задач обязаны явно выставлять:
- `work_kind = WorkKind.work`

Где:
- `app/api/tasks.py` → `create_task()`
- `app/services/deliverable_bootstrap_service.py` → bootstrap tasks

---

## 3. Архитектура слоёв

Проект построен по простому “слоистому” принципу:

- **API слой (`app/api`)**
  - входные точки FastAPI
  - RBAC checks
  - формирование response
  - никаких прямых “сложных доменных действий” (кроме простого CRUD)

- **Service слой (`app/services`)**
  - бизнес-операции и инварианты
  - транзакционные сценарии (bootstrap, fix создание, transitions)

- **FSM слой (`app/fsm`)**
  - чистая логика переходов статусов
  - возвращает `to_status` и `side_effects`

- **Models слой (`app/models`)**
  - SQLAlchemy модели
  - минимум логики

- **Schemas слой (`app/schemas`)**
  - Pydantic модели для запросов/ответов
  - валидации (например notes required при QC reject)

---

## 4. RBAC (доступ)

Сервис внутренний (“all-locked”).
Роли приходят из `get_actor_role` (пока stub/заглушка).

Точки контроля:
- `ensure_allowed("deliverable.bootstrap", actor_role)`
- `ensure_allowed("deliverable.signoff", actor_role)`
- `ensure_allowed("deliverable.submit_to_qc", actor_role)`
- `ensure_allowed("deliverable.qc_decision", actor_role)`
- `ensure_allowed(f"task.{action}", actor_role)` для transitions

Файлы:
- `app/api/deps.py` — получение роли
- `app/core/rbac.py` — политика и `Forbidden`

---

## 5. Основные API (MVP)

### 5.1 Tasks
- `POST /tasks` — создать задачу (обычная работа, `work_kind=work`)
- `POST /{task_id}/transitions` — FSM переход + optimistic lock + idempotency
- `GET /tasks` — список задач
- `GET /tasks/{task_id}/transitions` — timeline
- dependencies:
  - `POST /tasks/{task_id}/dependencies`
  - `GET /tasks/{task_id}/dependencies`
  - `DELETE /tasks/{task_id}/dependencies/{predecessor_id}`
- blockers:
  - `GET /tasks/{task_id}/blockers`

### 5.2 Deliverables
- `POST /deliverables` — создать изделие
- `GET /deliverables` — список
- `GET /deliverables/{id}` — получить
- `POST /deliverables/{id}/bootstrap` — развернуть дерево задач
- `POST /deliverables/{id}/signoffs` — production signoff
- `POST /deliverables/{id}/submit_to_qc` — gate: нужен последний approved signoff
- `POST /deliverables/{id}/qc_decision` — approve/reject (reject создаёт fix-task через сервис)
- `GET /deliverables/{id}/qc_inspections`
- `GET /deliverables/{id}/tasks`
- `GET /deliverables/{id}/dashboard`
- `POST /deliverables/{id}/fix-tasks` — инициативный fix по изделию (через сервис)

---

## 6. Транзакционные сценарии

### 6.1 apply_task_transition (FSM)
Файл: `app/services/task_transition_service.py`

Сценарий:
1) idempotency check (по client_event_id)
2) lock `Task` (`SELECT ... FOR UPDATE`)
3) optimistic lock (row_version)
4) apply FSM
5) записать `TaskTransition`
6) side effects:
   - reject → создать fix-task через `TaskFixService` (не напрямую)
7) flush → ловим гонки/unique constraint

---

### 6.2 deliverable bootstrap
Файл: `app/services/deliverable_bootstrap_service.py`

Сценарий:
- читает template nodes
- создаёт tasks (пока без parent_task_id)
- flush для получения UUID
- проставляет parent_task_id
- создаёт dependencies

Инвариант:
- bootstrap всегда создаёт `work_kind=work`

---

### 6.3 QC decision reject
Файл: `app/api/deliverables.py`

При reject:
- пишет `QcInspection`
- flush (чтобы получить qc.id)
- создаёт fix-task через `TaskFixService.create_qc_reject_fix(...)`

---

## 7. База данных и миграции

- Postgres 16 (docker compose), контейнер: `planner_postgres`
- Alembic: `alembic/`

Команды:
- создать миграцию (автогенерация):
  - `alembic revision --autogenerate -m "message"`
- применить:
  - `alembic upgrade head`

Важно:
- миграции должны быть повторяемыми
- уникальность `(org_id, client_event_id)` защищает идемпотентность transitions

---

## 8. Dev запуск

Папка проекта (локально):
- `/Users/alex/PycharmProjects/planner`

Запуск:
1) Docker Desktop должен быть запущен
2) `docker compose up -d postgres`
3) `. .venv/bin/activate`
4) `alembic upgrade head`
5) `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`

---

## 9. Соглашения по патчам (обязательное правило)

При любом патче:
1) **всегда** указывать файл: `# path/to/file.py`
2) делать **минимальные изменения** (mini-patch)
3) не смешивать несколько задач/пунктов в одном сообщении
4) сначала фиксируем инвариант/страховку, потом рефакторинг

---

## 10. Что дальше (после API)

Следующие крупные блоки (по порядку полезности):
1) Тесты (FSM, invariants, qc reject flow, idempotency)
2) DB constraints / partial indexes (где можно усилить)
3) Auth (вместо org_id/actor_user_id в body/query)
4) UI/CLI сценарии для проверки end-to-end
