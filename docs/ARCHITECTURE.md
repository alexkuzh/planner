# Planner — Architecture (MVP)

## Goal
Planner — сервис для управления производственным процессом по изделиям (deliverables) на базе шаблонов работ (DNA).  
Стек: FastAPI + SQLAlchemy + Alembic + Postgres (docker-compose).  
Ключевая особенность: управление жизненным циклом задач через FSM transitions + аудит событий.

---

## Core domain concepts

### Deliverable (изделие / партия)
Deliverable — агрегат процесса. Это единица, которую реально выпускают/проверяют.

- В одном проекте **только один тип deliverable** (упрощение MVP).
- `serial` приходит извне (ERP/склад/заказ), внутри хранится как внешний идентификатор.
- Deliverable хранит `template_version_id` — по какому “чертежу” развернули дерево задач.

**Deliverable statuses (MVP):**
- `open`
- `submitted_to_qc`
- `qc_approved`
- `qc_rejected`

**Gate в QC (MVP):**
- deliverable можно переводить в `submitted_to_qc`, когда **все milestone tasks (`is_milestone=true`) = done**.
- Если milestone задач нет — gate считается пройденным.

---

### Task (работа)
Task — единица работы внутри deliverable.  
Структура задач представляет WBS дерево + зависимости (граф).

- `deliverable_id` может быть NULL для задач, не относящихся к конкретному изделию (maintenance/admin/other).
- `parent_task_id` — WBS-иерархия.
- `task_dependencies` — зависимости `predecessor → successor`.
- FSM + `task_events` фиксируют историю всех переходов.

**Task statuses (общая идея):**
- `new / planned / assigned / in_progress / in_review / rejected / done / canceled`

---

## Task classification (важно)

### `tasks.kind` — доменная классификация
`kind` описывает *что это за задача по природе* (домены/классы работ):

- `production`
- `maintenance`
- `admin`
- `other`

Это поле **НЕ** используется для различения “fix” задач.

### `tasks.work_kind` — тип работы (ортогонально `kind`)
`work_kind` описывает *тип выполнения*:

- `work` — обычная плановая работа
- `fix` — corrective / rework / исправление

`work_kind` ортогонален `kind`.  
Например: `kind=production` и `work_kind=fix` — исправление производственного дефекта.

---

## Fix-task (исправление)

### Что такое fix-task
Fix-task — это обычная Task со следующими признаками:

- `work_kind = fix`
- `fix_source` задан
- `fix_severity` задан (MVP: default `minor`, если не указано)
- `minutes_spent` опционально (для бонусов/аналитики)

Связи:
- `origin_task_id` — на какую задачу ссылается fix (если дефект обнаружен в конкретной задаче)
- `qc_inspection_id` — если fix породился официальным QC reject

### Источники fix-task (MVP)
`fix_source`:
- `qc_reject`
- `worker_initiative`
- `supervisor_request`

`fix_severity`:
- `minor`
- `major`
- `critical`

### Инварианты fix-task (MVP, обязаны соблюдаться)
- Если `work_kind = fix`:
  - `fix_source IS NOT NULL`
  - `fix_severity IS NOT NULL`
- Если `work_kind = work`:
  - `fix_source IS NULL`
  - `fix_severity IS NULL`

---

## Allocations (распределение на смену/дату)
Allocations — оперативное планирование (кто что делает в конкретный день/смену).

- Лид “раздаёт” задачи ежедневно.
- Allocation enrich’ится данными deliverable через join Task → Deliverable (serial и т.п.).
- Allocation не является доменной “истиной”, а отражает план/назначение.

---

## Sign-off and QC

### Production sign-off
`deliverable_signoffs` фиксирует, кто “подписал” изделие (точка ответственности).

**MVP смысл sign-off (scope=full):**
- “На момент подписи все задачи по deliverable выполнены”.

Подпись — это не замена QC, а фиксация ответственности в производстве.

### QC inspections
`qc_inspections` фиксирует решение отдела QC по deliverable.

- `approved` / `rejected`
- При `rejected` обязателен `reason`.

**При QC reject (MVP контракт):**
- `qc_inspection.reason` обязателен
- `responsible_user_id` вычисляется как `last approved signoff.signed_off_by`
  - fallback (если signoff нет): deliverable.created_by / supervisor проекта (по настройке)
- создаётся минимум один fix-task (`work_kind=fix`, `fix_source=qc_reject`, `qc_inspection_id` заполнен)
- deliverable.status становится `qc_rejected`

---

## DNA изделия (шаблоны)

### Entities
- `ProjectTemplate` — шаблон проекта (у проекта одна активная версия)
- `ProjectTemplateVersion` — версия “чертежа”
- `ProjectTemplateNode` — дерево работ
- `ProjectTemplateEdge` — зависимости

### Bootstrap service
Bootstrap создаёт инстанс задач из активной версии:

1) берёт активную `ProjectTemplateVersion`  
2) создаёт tasks (planned)  
3) строит parent-child  
4) копирует зависимости в `task_dependencies`  
5) проставляет `deliverable.template_version_id`

---

## MVP API (ориентир)

### Deliverables
- `POST /deliverables` — создать deliverable (serial приходит извне)
- `POST /deliverables/{id}/bootstrap` — развернуть задачи по активному шаблону
- `POST /deliverables/{id}/submit-to-qc` — gate: milestone done
- `POST /deliverables/{id}/signoff` — scope=full (все задачи done)
- `POST /deliverables/{id}/qc/inspect` — approve/reject

### Tasks
- `GET /deliverables/{id}/tasks`
- `POST /tasks/{id}/transition` — FSM action
- `POST /tasks/{id}/report-fix` — инициативный fix на origin_task

### Fix tasks
- `POST /deliverables/{id}/fix-tasks` — fix на deliverable без origin_task
- `GET /deliverables/{id}/fix-tasks` — список исправлений

---

## Permissions (MVP словами)
Права на ключевые действия (базовая модель):

- create deliverable: Project Owner / Intake
- bootstrap: Project Owner / Supervisor (или System)
- submit_to_qc: Lead / Worker (по правилам компании) + gate policy
- qc_decision: QC Department
- signoff(full): ответственный (Lead / Supervisor) — зависит от орг. структуры
- allocations: Lead

---

## Observability and audit
- Все переходы задач фиксируются в `task_events`.
- Важно избегать ручных правок статусов в БД: состояние должно меняться через сервисы/эндпоинты.

---

## Postponed (intentionally)
- M5: QC по milestone (milestone_task_id в qc_inspections)
- 16A/16B: QC очередь и отчёт возвратов QC по ответственным

---

## DevOps / Local run
- Postgres в docker-compose (контейнер `planner_postgres`)
- API можно запускать локально:
  - `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`

---

## Conventions
- `kind` (production/maintenance/...) ≠ `work_kind` (work/fix)
- Fix-task — не отдельная сущность, а Task с `work_kind=fix`.
- `template_version_id` в deliverable — snapshot, не меняется задним числом.
