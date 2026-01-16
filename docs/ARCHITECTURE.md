# ARCHITECTURE.md (v4)

## 1. Назначение системы

**Planner** — backend-система для управления производственными задачами с чёткой
доменной моделью, основанной на:

- конечных автоматах (FSM),
- строгой идемпотентности,
- оптимистической блокировке,
- разделении ответственности между доменами.

Ключевая цель архитектуры — **предсказуемость процессов**, **аудируемость**
и **устойчивость к ошибкам клиента** (повторы запросов, гонки, ретраи).

---

## 2. Доменные границы (Domain Boundaries)

### 2.1 Task — основной домен

**Task** — атомарная единица работы.

Свойства:
- принадлежит `org_id` и `project_id`,
- имеет статус (`status`) и версию (`row_version`),
- может быть связана с `deliverable`,
- изменяется **только** через FSM.

Запрещено:
- менять `status` напрямую через `PATCH`,
- создавать побочные эффекты вне FSM.

Все изменения статуса происходят через:
- `POST /tasks/{task_id}/transitions`

---

### 2.2 Task FSM (Finite State Machine)

FSM определяет допустимые переходы статусов задачи.

#### Статусы (final)

- blocked
- available
- assigned
- in_progress
- submitted
- done
- canceled

#### Основные действия (final)

- self_assign
- assign
- start
- submit
- review_approve
- review_reject
- shift_release
- recall_to_pool
- escalate

Примечания:
- FSM **не знает ролей**, API и БД.
- RBAC и idempotency обеспечиваются вне FSM.
- FSM возвращает только `(to_status, side_effects)`.

---

### 2.3 TaskTransition — журнал переходов

`TaskTransition` — **неизменяемый лог** всех FSM-переходов.

Назначение:
- аудит,
- восстановление истории,
- строгая идемпотентность,
- защита от race conditions.

Ключевые поля:
- `client_event_id` — ключ идемпотентности,
- `expected_row_version`,
- `result_row_version`,
- `payload` (нормализованный).

Правило:
> Если `client_event_id` уже использован — запрос либо повторяется,
> либо отклоняется как конфликт.

---

### 2.4 Fix и Defects (исправление дефектов)

**Fix-task** — отдельная задача, создаваемая при обнаружении дефекта.

Правила:
- Fix может быть создан из состояния исходной задачи **submitted** (дефект на проверке)
- Fix может быть создан из **done** (поздний дефект)
- Fix инициируется только `lead/supervisor`
- Fix всегда связан с исходной задачей (`fix_of_task_id`)
- Каждый Fix **обязан** иметь запись дефекта (**Defect**):
  - причина/описание
  - что исправить
  - как исправлено
  - кто и когда исправил

Fix-task проходит тот же FSM, что и обычные задачи.
Fix — бизнес-сценарий поверх Task, а не отдельный поддомен.

---

### 2.5 QC (Quality Control) — отдельный домен

QC — домен качества на уровне `deliverable` (инспекции, измерения, акты).

Принцип (зафиксирован):
- QC **не управляет Task напрямую**
- QC работает через `deliverable` и `qc_inspections`
- QC может инициировать создание `Defect` и `Fix-task`, но не переводит Task по статусам

Важно:
- Task-level переходы `review_approve/review_reject` — это **Review/Acceptance** (приёмка результата работы),
  а не deliverable-level QC inspection.
- Любые действия вида `qc_*` запрещены в `/tasks/{id}/transitions`.

---

## 3. Роли и RBAC

RBAC проверяется **на уровне API**, а не FSM.

FSM:
- не знает ролей,
- не принимает решений о доступе.

RBAC:
- сопоставляет `role → permission`,
- разрешения привязаны к действиям (`task.self_assign`, `task.assign`, и т.д.).

Роли:
- `executor`
- `lead`
- `supervisor`
- `system`

---

## 4. Идемпотентность

Каждый mutating-запрос содержит `client_event_id`.

Поведение:
- тот же `client_event_id` + тот же смысл → safe retry,
- тот же `client_event_id` + другие данные → `409 Conflict`.

Для сравнения:
- payload нормализуется,
- серверные поля игнорируются.

---

## 5. Оптимистическая блокировка

Используется `row_version`.

Правило:
- клиент обязан передать `expected_row_version`,
- если версия не совпадает — `409 Conflict`.

Это:
- защищает от lost update,
- не требует `SELECT ... FOR UPDATE`,
- хорошо масштабируется.

---

## 6. Task Execution Architecture (Pool-based Assignment)

### 6.1 Core execution model

Система использует **pull-модель выполнения задач**, управляемую сменами и ролями:

- задачи попадают в **пул доступных задач** (`available`)
- исполнитель **выбирает задачу** и становится её **primary executor (owner)**
- над задачей могут работать **несколько исполнителей** (contributors)
- только **owner** управляет жизненным циклом задачи (start/submit)
- лидер и супервайзер сохраняют **полный контроль**: назначение, отзыв, переназначение

Назначение задачи всегда **временно** и ограничено **сменой**.

### 6.2 Specialization (trade)

Executor может иметь несколько специализаций:

- `specializations: Set[Trade]`

Task может требовать специализацию:

- `required_trade: Trade | null`

Правило:
- executor видит/берёт задачи, если `required_trade is null` или входит в `executor.specializations`.

### 6.3 Skill model (trust & autonomy)

- `skill_level: int (1–10)`

Skill отражает уровень доверия.

Skill:
- **не влияет** на принадлежность задачи пулу
- влияет на:
  - видимость pool projection для executor (порог)
  - возможность self-assign (порог)
  - возможность self-check / автономной приёмки (порог)
  - право отправлять invites contributors (high-skill)

Глобальные пороги:
- `MIN_SKILL_TO_TAKE`
- `SELF_CHECK_MIN_SKILL`
- `MIN_SKILL_TO_INVITE` (если используем делегированные инвайты)

### 6.4 Participation model

Owner:
- всегда один
- может иметь только одну активную задачу (WIP=1)
- только owner делает `submit`

Contributors:
- invite-only: добавляет `lead/supervisor`, либо owner с высоким skill (делегировано)
- не меняют статус задачи
- не могут submit

Ответственность:
- за результат отвечает owner, который сделал `submit`.

---

## 7. Controlled Return to Pool + Escalation

Возврат задачи в пул из `in_progress` допускается **только**:

- `shift_release` (system, конец смены)
- `recall_to_pool` (lead/supervisor, принудительный отзыв/переназначение)

Executor не может сам вернуть задачу в пул из `in_progress`.

### Escalation

Чтобы избежать тупиков, есть `escalate`:

- `escalate` не меняет статус задачи и не снимает owner
- сигнализирует lead/supervisor, что нужна помощь/решение:
  - материалы/инструменты/доступ
  - пересечение работ
  - нужна помощь/команда
  - задача сложнее ожидаемого

Lead/supervisor реагирует:
- добавляет contributors
- даёт инструкцию
- переназначает owner
- отзывает в пул (`recall_to_pool`)
- дробит на подзадачи

---

## 8. Task Pool Architecture (Golden Standard)

### Core Principle

Domain pool = Task.status == 'available' (single source of truth)

'available' is a GUARANTEE, not a filter result.


### 8.1 Three-Level Architecture

1) Domain truth:
- `domain_pool = tasks WHERE status == 'available'`

2) Access projection (visibility):
- lead/supervisor/system: видят весь domain_pool
- executor:
  - если `skill < MIN_SKILL_TO_TAKE` → видит пусто
  - иначе видит задачи по своим `specializations` (trade-match)

3) Action authorization:
- видимость задачи не гарантирует право действия
- self-assign требует WIP=1 и порогов skill

### 8.2 Invariants for `available`

Task может быть `available` iff:
- dependencies satisfied
- no business holds
- `assigned_to IS NULL`
- not terminal

Инварианты проверяются **до** перевода в available.

### 8.3 Maintaining available status

Primary: event-driven (после закрытия predecessor / снятия hold / shift_release)
Optional: safety-net reconciliation job (периодически открывает готовые задачи, если событие было пропущено)

---

## 9. API — ответственность эндпоинтов

### 9.1 /tasks
- `POST /tasks` — создание задачи
- `PATCH /tasks/{id}` — изменение метаданных (НЕ статус)
- `DELETE /tasks/{id}` — удаление (RBAC + guard)

### 9.2 /tasks/{id}/transitions
Единственный способ:
- менять статус
- фиксировать историю
- создавать side-effects (например: create_fix)

### 9.3 /tasks/{id}/report-defect (опционально)
Worker-initiative сценарий:
- создание Defect записи
- без прямого влияния на FSM исходной задачи
- дальнейшие решения (создание fix) принимает lead/supervisor

---

## 10. Архитектурные принципы

1. **FSM — чистая логика**
2. **API — только оркестрация**
3. **Сервисы — бизнес-правила**
4. **TaskTransition — источник истины аудита**
5. **QC (deliverable) отделён от Task**
6. **Идемпотентность обязательна**
7. **Один запрос — одно намерение**
8. **Пул = available (single source of truth)**
9. **Контролируемый возврат в пул + escalate**

---

## 11. Зафиксированные решения (v4)

- `planned` исключён
- Пул задач = `status == available`
- Возврат в пул из `in_progress` только через `shift_release` и `recall_to_pool`
- `escalate` обязателен как выход из тупиков (без снятия owner)
- Contributors invite-only (lead/supervisor или high-skill owner)
- Fix создаётся из `submitted` и `done`, всегда с Defect записью
- Review/Acceptance task-level != deliverable-level QC inspections
- status нельзя менять через update, только через transitions
- idempotency строгая
- row_version обязателен

---

**ARCHITECTURE.md v4 зафиксирован.**


## Task FSM Contract (v4)

Этот раздел — **единственный контракт** переходов статусов Task.
Любая реализация (`task_fsm.py`, сервисы, API) должна соответствовать таблице ниже.

### Statuses

- blocked
- available
- assigned
- in_progress
- submitted
- done
- canceled

### Actions

- self_assign
- assign
- start
- submit
- review_approve
- review_reject
- shift_release
- recall_to_pool
- escalate
- cancel

> Примечание: `escalate` — событие/флаг, **не меняет статус** (см. таблицу).

---

### Transition table

| From        | Action          | To          | Actor roles                | Guards (must hold) | Side-effects |
|-------------|------------------|-------------|----------------------------|--------------------|-------------|
| blocked     | unblock          | available   | system / lead / supervisor | all deps satisfied; no holds; assigned_to is NULL; not terminal | none |
| available   | self_assign      | assigned    | executor                   | skill >= MIN_SKILL_TO_TAKE; trade match (or required_trade NULL); executor primary WIP=0; assigned_to is NULL; row_version matches | set assigned_to=executor; assigned_at=now |
| available   | assign           | assigned    | lead / supervisor          | target executor primary WIP=0; (trade override allowed only if policy permits); assigned_to is NULL; row_version matches | set assigned_to=target; assigned_by=actor; assigned_at=now |
| assigned    | start            | in_progress | owner (primary executor)   | actor == assigned_to; row_version matches | set started_at=now (if tracked) |
| in_progress | submit           | submitted   | owner (primary executor)   | actor == assigned_to; row_version matches | set submitted_at=now (if tracked) |
| submitted   | review_approve   | done        | lead / supervisor          | row_version matches | set reviewed_by=actor; reviewed_at=now (if tracked) |
| submitted   | review_approve   | done        | owner (primary executor)   | actor == assigned_to; skill >= SELF_CHECK_MIN_SKILL; row_version matches | set self_checked=true; reviewed_at=now (if tracked) |
| submitted   | review_reject    | in_progress | lead / supervisor          | row_version matches | record reject reason; optionally create Defect and/or create Fix-task |
| assigned    | shift_release    | available   | system                     | end-of-shift; assigned_to not NULL; invariants for available still hold; row_version matches | clear assigned_to; clear contributors; clear assigned_by/assigned_at if desired |
| in_progress | shift_release    | available   | system                     | end-of-shift; invariants for available still hold; row_version matches | clear assigned_to; clear contributors |
| assigned    | recall_to_pool   | available   | lead / supervisor          | row_version matches; invariants for available still hold | clear assigned_to; clear contributors; record recall reason |
| in_progress | recall_to_pool   | available   | lead / supervisor          | row_version matches; invariants for available still hold | clear assigned_to; clear contributors; record recall reason |
| *           | escalate         | (no change) | owner / contributor         | actor participates in task; row_version matches (optional) | create escalation record/event; set needs_attention=true |
| available   | cancel           | canceled    | lead / supervisor          | row_version matches | record cancel reason |
| assigned    | cancel           | canceled    | lead / supervisor          | row_version matches | clear assigned_to; record cancel reason |
| in_progress | cancel           | canceled    | lead / supervisor          | row_version matches | clear assigned_to; record cancel reason |
| submitted   | cancel           | canceled    | lead / supervisor          | row_version matches | record cancel reason |

---

### Notes & invariants

#### Available invariants (must be true whenever status == available)
- dependencies satisfied
- no business holds
- assigned_to IS NULL
- not terminal

#### Controlled return to pool
From `in_progress` to `available` is allowed **only** via:
- `shift_release` (system)
- `recall_to_pool` (lead/supervisor)

Executor cannot return a task to pool from `in_progress`.

#### Ownership & responsibility
- Only owner can `start` and `submit`.
- Responsibility for outcome is on the owner who performs `submit`.

#### Contributors (policy)
- Contributors are invite-only (lead/supervisor or high-skill owner via delegated invites).
- Contributors cannot change status and cannot submit.
