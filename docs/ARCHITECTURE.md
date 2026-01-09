# Planner — Architecture Overview

## 1. Цель системы

Planner — это backend-система для управления производственными изделиями (deliverables), деревьями задач и контролем качества.

Основная цель:

* обеспечить **прозрачный жизненный цикл изделия** от старта производства до QC-утверждения;
* зафиксировать **ответственность** (sign-off) и **причины возвратов** (QC reject);
* позволить расширение (milestones, QC-очереди, аналитика бонусов) без ломки ядра.

Текущий фокус — **MVP**, с чётко зафиксированными инвариантами и отложенными фичами.

---

## 2. Технологический стек

* Python 3.13
* FastAPI (REST API + Swagger)
* SQLAlchemy ORM
* Alembic (миграции)
* PostgreSQL (Docker Compose)
* FSM (явные переходы задач)

---

## 3. Ключевые доменные сущности

### 3.1 Deliverable (изделие)

Центральный агрегат домена.

**Смысл:** конкретное изделие (или партия), производимое по шаблону.

**Ключевые поля:**

* `id`
* `org_id`, `project_id`
* `serial` (приходит извне)
* `template_version_id` — по какой версии шаблона создано
* `status`:

  * `open`
  * `submitted_to_qc`
  * `qc_approved`
  * `qc_rejected`

**Важно:**

* статус deliverable — **агрегатный**, не меняется вручную;
* зависит от sign-off и QC decision.

---

### 3.2 Task (задача)

Работы по изделию, образуют дерево (WBS).

**Связи:**

* `deliverable_id` — может быть NULL (admin / maintenance / прочее)
* `parent_task_id` — иерархия
* `task_dependencies` — зависимости (predecessor → successor)

**Жизненный цикл:**

* управляется FSM (`task_fsm.py`)
* все переходы аудируются (`task_transitions`, `task_events`)

**Ключевые поля:**

* `status`
* `priority`
* `is_milestone`

---

### 3.3 Fix-task (исправление)

**Fix-task — это НЕ отдельная сущность.**

Это обычный `Task` со следующими признаками:

* `work_kind = fix`
* `fix_source`:

  * `qc_reject`
  * `worker_initiative`
  * `supervisor_request`
* `fix_severity`: `minor | major | critical`
* опционально:

  * `origin_task_id`
  * `qc_inspection_id`

**Инварианты:**

* QC reject **обязан** создать минимум один fix-task
* fix-task участвует в аналитике и бонусах

---

### 3.4 DeliverableSignoff (production sign-off)

**Точка ответственности.**

Фиксирует, кто подтвердил готовность изделия к QC.

**Поля:**

* `signed_off_by`
* `result`: `approved | rejected`
* `comment`

**Правило:**

* `submit_to_qc` разрешён только если последний sign-off = `approved`
* при QC reject `responsible_user_id` берётся из **последнего approved sign-off**

---

### 3.5 QC Inspection

Решение отдела контроля качества.

**Поля:**

* `result`: `approved | rejected`
* `notes` (обязательно при reject)
* `inspector_user_id`
* `responsible_user_id`

**Поведение:**

* `approved` → deliverable.status = `qc_approved`
* `rejected` →

  * deliverable.status = `qc_rejected`
  * создаётся fix-task (`fix_source = qc_reject`)

---

## 4. Шаблоны (DNA изделия)

### 4.1 ProjectTemplateVersion

Определяет структуру изделия:

* узлы (`ProjectTemplateNode`)
* зависимости (`ProjectTemplateEdge`)

Один проект использует **одну активную версию** шаблона.

---

### 4.2 Bootstrap

`POST /deliverables/{id}/bootstrap`

**Назначение:**

* развернуть задачи по шаблону
* создать дерево задач
* скопировать зависимости

**Особенности:**

* системное действие
* **НЕ требует actor_user_id**
* не влияет на ответственность

---

## 5. API-соглашения

### 5.1 Command

Для пользовательских действий используется обёртка:

* `Command[T]`
* содержит: `org_id`, `actor_user_id`, `expected_row_version`, `client_event_id`, `payload`

Используется в:

* transitions
* report-fix
* deliverable fix-tasks

---

### 5.2 Query vs Body

* **Query:** системный контекст (org_id, project_id) — временно, до auth
* **Body:** доменные действия

---

## 6. Инварианты (обязательные правила)

1. QC reject → минимум один fix-task
2. QC reject → `responsible_user_id` = last approved sign-off
3. Deliverable status не меняется напрямую
4. Sign-off — единственная точка ответственности
5. Bootstrap не требует пользователя
6. Fix-task всегда `work_kind = fix`

---

## 7. Отложено сознательно

* **M5:** QC по milestone (`milestone_task_id` в qc_inspections)
* **16A:** QC очередь
* **16B:** отчёт возвратов QC по ответственным
* Auth-context (замена org_id/query)
* Расширенные роли (supervisor / lead / worker)

---

## 8. Объём и ожидания MVP

* ~1 deliverable в неделю
* ~50–200 задач на deliverable
* Один тип deliverable в проекте
* Serial приходит извне

---

## 9. Принципы дальнейшего развития

* Не плодить сущности без необходимости
* Явные инварианты важнее гибкости
* Swagger = пользовательская документация
* Сначала корректность, потом оптимизация

---

**Статус документа:** зафиксирован под текущий MVP
