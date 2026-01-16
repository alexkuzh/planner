# ARCHITECTURE.md (v3)

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

POST /tasks/{task_id}/transitions

---

### 2.2 Task FSM (Finite State Machine)

FSM определяет допустимые переходы статусов задачи.

#### Статусы

- new
- planned
- assigned
- in_progress
- in_review
- rejected
- done
- canceled


#### Основные действия

- plan
- assign
- unassign
- start
- submit
- approve
- reject


FSM:
- **не знает ролей**,
- **не знает API**,
- **не знает БД**,
- возвращает только `(to_status, side_effects)`.

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

### 2.4 Fix-task (исправление дефектов)

**Fix-task** — отдельная задача, создаваемая при обнаружении дефекта.

Создание:
- автоматически как side-effect FSM-действия `reject`,
- вручную через worker initiative (`/report-fix`).

Свойства:
- всегда привязана к `deliverable`,
- не «возвращает» основную задачу автоматически,
- проходит **тот же FSM**, что и обычные задачи.

Fix-task — **не поддомен Task**, а отдельный бизнес-сценарий поверх него.

---

### 2.5 QC (Quality Control) — отдельный домен

QC **не является частью Task FSM**.

Принцип (Variant A, зафиксирован):
- QC **не переводит Task по статусам**,
- QC работает через `deliverable` и `qc_inspections`,
- результаты QC могут **инициировать** создание fix-task,
  но не управляют Task напрямую.

### Любые действия вида: qc_*
запрещены в `/tasks/{id}/transitions`.

---

## 3. Роли и RBAC

RBAC проверяется **на уровне API**, а не FSM.

FSM:
- не знает ролей,
- не принимает решений о доступе.

RBAC:
- сопоставляет `role → permission`,
- разрешения привязаны к действиям (`task.plan`, `task.assign`, и т.д.).

Пример:

task.plan → system, lead

task.assign → lead, supervisor

task.approve → lead, supervisor

fix.qc_reject → qc


---

## 4. Идемпотентность

Каждый mutating-запрос может содержать `client_event_id`.

Поведение:
- тот же `client_event_id` + тот же смысл → safe retry,
- тот же `client_event_id` + другие данные → `409 Conflict`.

Для сравнения:
- payload нормализуется,
- серверные поля (например `fix_task_id`) игнорируются.

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

## 6. API — ответственность эндпоинтов

### 6.1 /tasks

- `POST /tasks` — создание задачи,
- `PATCH /tasks/{id}` — изменение метаданных (НЕ статус),
- `DELETE /tasks/{id}` — удаление (RBAC + guard).

### 6.2 /tasks/{id}/transitions

Единственный способ:
- менять статус,
- создавать fix-task,
- фиксировать историю.

### 6.3 /tasks/{id}/report-fix

Worker-initiative сценарий:
- фиксация дефекта,
- создание новой fix-task,
- без влияния на FSM исходной задачи.

---

## 7. Архитектурные принципы

1. **FSM — чистая логика**
2. **API — только оркестрация**
3. **Сервисы — бизнес-правила**
4. **TaskTransition — источник истины**
5. **QC отделён от Task**
6. **Идемпотентность обязательна**
7. **Один запрос — одно намерение**

---

## 8. Зафиксированные решения (v3)

- QC не управляет Task напрямую
- status нельзя менять через update
- все переходы только через FSM
- fix-task — отдельный сценарий
- idempotency строгая
- row_version обязателен

---

## 9. Что дальше (v4+)

- QC milestones
- Deliverable lifecycle
- Read-models (CQRS)
- UI/CLI сценарии
- Event streaming (опционально)

---

**ARCHITECTURE.md v3 зафиксирован.**

# UPDATE
# Task Execution Architecture
## Pool-based Assignment · Shift Ownership · Skill-gated Responsibility

---

## 1. Core execution model

Система использует **pull-модель выполнения задач**, управляемую сменами и ролями:

- задачи попадают в **пул доступных задач** (`available`)
- исполнитель **выбирает задачу** и становится её **primary executor (owner)**
- над задачей могут работать **несколько исполнителей** (contributors)
- только **owner** управляет жизненным циклом задачи (start/submit)
- лидер и супервайзер сохраняют **полный контроль**: назначение, отзыв, переназначение, контроль качества

Назначение задачи всегда **временно** и ограничено **сменой**.

---

## 2. Roles

- **executor** — выполняет работу, может быть owner или contributor  
- **lead / supervisor** — управляет распределением, проверкой, фиксацией дефектов  
- **system** — выполняет автоматические переходы (например, окончание смены)

---

## 3. Specialization (trade)

### Executor
Исполнитель может иметь **несколько специализаций**:

```
specializations: Set[Trade]
```

Специализация используется для:
- видимости пула задач
- возможности стать primary executor

### Task
Задача может требовать одну специализацию:

```
required_trade: Trade | null
```

**Правило соответствия:**  
executor может взять задачу, если  
`required_trade is null OR required_trade ∈ executor.specializations`

---

## 4. Skill model (trust & autonomy)

### Skill level
```
skill_level: int (1–10)
```

Skill отражает **уровень доверия**, а не допуск к работе.

Skill **НЕ влияет** на:
- видимость пула
- возможность присоединиться к задаче (contributor)

Skill **влияет** на:
- возможность стать primary executor (self-assign)
- возможность самопроверки (self-QC)

### Global thresholds
- `MIN_SKILL_TO_TAKE` — минимальный skill, чтобы **выбрать задачу**
- `SELF_CHECK_MIN_SKILL` — минимальный skill для **самопроверки без лида**

---

## 5. Task participation model

### Primary executor (owner)
- всегда **один**
- выбирает задачу из пула или назначается лидом
- управляет статусом выполнения
- делает submit
- может выполнять self-QC (если позволяет skill)

### Contributors
- 0..N исполнителей
- помогают в выполнении
- **не могут** менять статус задачи
- могут быть добавлены/удалены лидом
- могут покинуть задачу

---

## 6. Work-in-Progress constraints

- **Owner WIP = 1**  
  Исполнитель может быть primary executor **только одной активной задачи**.

---

## 7. Task pool (`available`)

Задача находится в пуле, если:
- не назначен primary executor
- выполнены зависимости
- нет блокировок
- задача не завершена

### Видимость пула
- **lead/supervisor** — видят весь пул
- **executor**:
  - если `skill < MIN_SKILL_TO_TAKE` → пул **не видит**
  - иначе видит пул **только по своим специализациям**

---

## 8. FSM rules (high-level)

### Назначение
- `available → assigned`
  - `self_assign` (executor)
  - `assign` (lead/supervisor)

### Выполнение
- `assigned → in_progress`
- `in_progress → submitted`

### Контроль качества
- `submitted → done` — self-QC
- `submitted → done` — QC approve
- `submitted → in_progress` — QC reject

---

## 9. Возврат в пул

Из `in_progress` задача возвращается в пул **только**:
- по окончании смены (`shift_release`)
- по отзыву лидом (`recall_to_pool`)

---

## 10. Shift semantics

- Назначение действует **только в рамках смены**
- В конце смены система:
  - снимает owner
  - завершает contributors
  - возвращает задачу в пул

---

## 11. Fix flow

- Fix создаётся **только после submit/done**
- Инициируется **lead/supervisor**
- Fix — отдельная задача, связанная с оригинальной

---

## 12. Defects

Для каждого фикса фиксируется дефект:
- причина
- что исправить
- как исправлено
- кто и когда

Формируется **база ошибок**.

---

## 13. Task catalog & tree

### TaskTemplate
- иерархия операций
- регламенты
- материалы и инструменты

### Task
- экземпляр выполнения
- ссылка на template

---

## 14. Recommendations (future)

Рекомендации строятся на основе:
- дерева операций
- истории дефектов
- пересечений по материалам и инструментам

---

## 15. Design principles

- Один owner — много contributors
- Skill = доверие
- Специализация = поток работ
- Пул — только выполнимые задачи
- Возврат в пул — контролируемый
- Исключения лидом — аудируемые


---

## Task Pool Architecture (Golden Standard)

**Status:** Зафиксировано 2026-01-15  
**Scope:** Production-ready архитектура пула задач

---

### Core Principle
```
Domain pool = Task.status == 'available' (single source of truth)

'available' is a GUARANTEE, not a filter result.
```

**Ключевое отличие от фильтрации:**
- ❌ Плохо: выбрать все задачи → отфильтровать заблокированные → показать пул
- ✅ Хорошо: статус `available` гарантирует готовность → показать пул

---

### 1. Three-Level Architecture

Чёткое разделение уровней абстракции:

#### Level 1: Domain Truth (membership)

Задача либо в пуле, либо нет. Это объективный факт.
```
Domain pool = { task | task.status == 'available' }
```

Определяется **только доменными правилами**, не зависит от того, кто смотрит.

#### Level 2: Access Projection (visibility)

Разные роли видят разные проекции пула.
```
pool_projection(actor) = domain_pool
  .filter(role_policy)
  .filter(skill_gate)
  .filter(trade_match)
```

**Lead/Supervisor:**
```python
pool_projection = domain_pool  # full visibility
```

**Executor:**
```python
if executor.skill < MIN_SKILL_TO_TAKE:
    pool_projection = []  # не видит пул
else:
    pool_projection = domain_pool
        .filter(required_trade IS NULL OR required_trade IN executor.specializations)
```

#### Level 3: Action Authorization (what can be done)

Видимость задачи — необходимое, но недостаточное условие.
```python
can_self_assign(executor, task) =
    task IN pool_projection(executor)
    AND executor.wip < 1
    AND (task.min_skill IS NULL OR executor.skill >= task.min_skill)
```

---

### 2. Status Model
```
blocked      : has unresolved dependencies OR business hold
planned      : ready by dependencies, waiting for process/shift start
available    : ready to be picked (POOL)
assigned     : has owner for current shift
in_progress  : work started
submitted    : waiting for QC/review
done         : completed
canceled     : aborted
```

**Transition flow (happy path):**
```
blocked → planned → available → assigned → in_progress → submitted → done
```

**Key transitions:**
- `blocked → planned` : when last dependency resolved
- `planned → available` : when business rules allow (no holds, materials ready)
- `available → assigned` : executor picks OR lead assigns
- `assigned → available` : shift_release OR recall_to_pool

---

### 3. Invariants for `available`

Task can be in `available` status **if and only if**:

1. ✅ All dependencies satisfied (`COUNT(predecessors WHERE status != done) == 0`)
2. ✅ No business holds (materials available, QC cleared, etc)
3. ✅ `assigned_to IS NULL`
4. ✅ Not in terminal status (`done`, `canceled`)

**Critical:** These are **preconditions** checked BEFORE transition, not filters applied after.

---

### 4. Maintaining `available` Status

#### A. Event-Driven Updates (Primary Mechanism)
```python
# When predecessor completes
def on_task_completed(task: Task, db: Session) -> list[Task]:
    """
    Triggered when task transitions to 'done'.
    Checks all successors and attempts to unblock them.
    
    Returns: list of tasks that became available
    """
    successors = get_successors(task, db)
    
    newly_available = []
    for succ in successors:
        if try_transition_to_available(succ, db):
            newly_available.append(succ)
    
    return newly_available

# When shift releases owner
def on_shift_release(task: Task, db: Session):
    """
    assigned → available (if preconditions still met)
    
    IMPORTANT: recheck dependencies (might have changed)
    """
    if task.status == TaskStatus.assigned.value:
        if can_transition_to_available(task, db):
            task.status = TaskStatus.available.value
            task.assigned_to = None
            task.assigned_at = None

# When QC releases hold
def on_hold_released(task: Task, db: Session):
    """Similar logic for business holds."""
    try_transition_to_available(task, db)
```

#### B. Safety Net (Background Job, Optional)
```python
# Periodic reconciliation (every 5-10 minutes)
def reconcile_available_status(db: Session, org_id: UUID):
    """
    Catches edge cases where event-driven updates missed something.
    
    Finds tasks in blocked/planned that should be available.
    """
    candidates = db.query(Task).filter(
        Task.org_id == org_id,
        Task.status.in_([TaskStatus.blocked, TaskStatus.planned]),
        Task.assigned_to.is_(None),
    ).all()
    
    for task in candidates:
        try_transition_to_available(task, db)
```

**Rationale:** Event-driven is sufficient for 99% cases, but safety net prevents "stuck" tasks.

---

### 5. `transition_to_available` — Atomic Implementation
```python
def try_transition_to_available(
    task: Task,
    db: Session,
    *,
    lock: bool = True,
) -> bool:
    """
    Atomically transition task to available if preconditions met.
    
    Returns:
        True if successfully transitioned
        False if preconditions not met
    
    Design notes:
    - Uses optimistic locking (row_version)
    - Checks ALL invariants
    - Does NOT raise exceptions (background-safe)
    - Idempotent (safe to call multiple times)
    """
    
    if lock:
        current_version = task.row_version
    
    # 1. Check dependencies
    blockers_count = db.execute(
        text("""
            SELECT COUNT(*)
            FROM task_dependencies d
            JOIN tasks t ON t.id = d.predecessor_id
            WHERE d.org_id = :org_id
              AND d.successor_id = :task_id
              AND t.status <> 'done'
        """),
        {"org_id": str(task.org_id), "task_id": str(task.id)},
    ).scalar_one()
    
    if blockers_count > 0:
        # transition to blocked if not already
        if task.status != TaskStatus.blocked.value:
            task.status = TaskStatus.blocked.value
            task.row_version += 1
        return False
    
    # 2. Check business holds (extensibility point)
    # if has_business_hold(task, db):
    #     return False
    
    # 3. Check not assigned
    if task.assigned_to is not None:
        return False
    
    # 4. Check not terminal
    if task.status in (TaskStatus.done.value, TaskStatus.canceled.value):
        return False
    
    # 5. Transition
    if task.status != TaskStatus.available.value:
        task.status = TaskStatus.available.value
        task.row_version += 1
        db.add(task)
        
        if lock:
            db.flush()
            db.refresh(task)
            # verify optimistic lock
            if task.row_version != current_version + 1:
                db.rollback()
                return False
    
    return True
```

---

### 6. Pool Query (Production-Ready)
```python
# app/services/task_pool_service.py

class TaskPoolService:
    """
    Отвечает за domain pool + access projection.
    НЕ отвечает за FSM transitions или RBAC.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_pool_projection_query(
        self,
        org_id: UUID,
        project_id: UUID,
        actor: Actor,
    ) -> Query[Task]:
        """
        Returns lazy query for pool projection (no .all()).
        
        Domain truth: status == 'available'
        Access policy: role + skill + trade
        
        Safety: includes assigned_to IS NULL as invariant check
        (belt-and-suspenders until system is battle-tested).
        """
        
        query = (
            self.db.query(Task)
            .filter(
                Task.org_id == org_id,
                Task.project_id == project_id,
                Task.status == TaskStatus.available.value,
                Task.assigned_to.is_(None),  # invariant safety check
            )
        )
        
        # Access filtering
        if actor.role == "executor":
            # skill gate
            if actor.skill_level < MIN_SKILL_TO_TAKE:
                return query.filter(sql.false())  # empty result
            
            # trade filtering
            if actor.specializations:
                query = query.filter(
                    or_(
                        Task.required_trade.is_(None),
                        Task.required_trade.in_(
                            [t.value for t in actor.specializations]
                        ),
                    )
                )
        
        elif actor.role not in ("lead", "supervisor", "system"):
            return query.filter(sql.false())  # empty result
        
        return query
    
    def get_pool_projection(
        self,
        org_id: UUID,
        project_id: UUID,
        actor: Actor,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """
        Materializes pool projection with pagination.
        
        Sorting strategy:
        - priority DESC (high priority first)
        - created_at ASC (older tasks first, FIFO fairness)
        - id ASC (stable sort for identical timestamps)
        """
        
        query = self.get_pool_projection_query(org_id, project_id, actor)
        
        return (
            query
            .order_by(
                Task.priority.desc(),
                Task.created_at.asc(),
                Task.id.asc(),  # stability
            )
            .limit(limit)
            .offset(offset)
            .all()
        )
```

**Why this works:**
- Single SQL query (no N+1)
- Honest pagination (no post-filtering)
- Blockers never in `available` (guaranteed by FSM)
- Fast with proper indexes

---

### 7. Required Indexes
```sql
-- Domain pool lookup
CREATE INDEX ix_tasks_org_project_status_unassigned 
ON tasks (org_id, project_id, status) 
WHERE assigned_to IS NULL;

-- Dependency checks (for try_transition_to_available)
CREATE INDEX ix_task_deps_successor 
ON task_dependencies (org_id, successor_id);

CREATE INDEX ix_task_deps_predecessor 
ON task_dependencies (org_id, predecessor_id);

-- Status check for predecessors
CREATE INDEX ix_tasks_id_status 
ON tasks (id, status);

-- Trade filtering (executor pool projection)
CREATE INDEX ix_tasks_org_project_status_trade
ON tasks (org_id, project_id, status, required_trade)
WHERE assigned_to IS NULL;

-- Pool ordering (covers ORDER BY in get_pool_projection)
CREATE INDEX ix_tasks_pool_ordering
ON tasks (org_id, project_id, priority DESC, created_at ASC, id ASC)
WHERE status = 'available' AND assigned_to IS NULL;
```

---

### 8. Race Condition Protection

**Scenario:** Two executors simultaneously pick the same task.

**Protection:** Optimistic locking + atomic transition
```python
def self_assign(
    task: Task,
    executor_id: UUID,
    expected_row_version: int,
    db: Session,
) -> Task:
    """
    Atomic self-assign with race protection.
    
    Preconditions:
    - task.status == 'available'
    - task.assigned_to IS NULL
    - executor.wip < 1
    - row_version matches (optimistic lock)
    
    Raises:
    - VersionConflict if row_version mismatch
    - TransitionNotAllowed if preconditions fail
    """
    
    # optimistic lock
    if task.row_version != expected_row_version:
        raise VersionConflict(
            f"Expected row_version={expected_row_version}, "
            f"actual={task.row_version}"
        )
    
    # preconditions
    if task.status != TaskStatus.available.value:
        raise TransitionNotAllowed("Task not available")
    
    if task.assigned_to is not None:
        raise TransitionNotAllowed("Task already assigned")
    
    # check executor WIP
    current_wip = db.query(Task).filter(
        Task.org_id == task.org_id,
        Task.assigned_to == executor_id,
        Task.status.in_([
            TaskStatus.assigned.value,
            TaskStatus.in_progress.value,
        ]),
    ).count()
    
    if current_wip >= 1:
        raise TransitionNotAllowed("WIP limit exceeded")
    
    # transition
    task.status = TaskStatus.assigned.value
    task.assigned_to = executor_id
    task.assigned_at = datetime.now(timezone.utc)
    task.row_version += 1
    
    db.add(task)
    db.flush()  # force write immediately, catch violations
    
    return task
```

**What happens on race:**
1. Executor A reads task (row_version=5)
2. Executor B reads task (row_version=5)
3. Executor A assigns → row_version=6, flush succeeds
4. Executor B tries assign → row_version mismatch → VersionConflict
5. Executor B retries, sees task already assigned → pool empty

---

### 9. Layer Responsibilities (Clean Architecture)

| Component | Responsibility | DB Access? |
|-----------|----------------|-----------|
| **Model** (`app/models/task.py`) | Data + simple computed properties | ❌ No |
| **FSM** (`app/fsm/task_fsm.py`) | Domain rules for transitions | ❌ No (pure logic) |
| **Pool Service** (`app/services/task_pool_service.py`) | Domain pool + access projection | ✅ Yes (queries only) |
| **Dependency Service** (`app/services/task_dependency_service.py`) | Event-driven status updates | ✅ Yes |
| **Transition Service** (`app/services/task_transition_service.py`) | Apply FSM + side effects | ✅ Yes |
| **RBAC** (`app/core/rbac.py`) | Permission checks | ❌ No |
| **API** (`app/api/tasks.py`) | Orchestration only | ❌ No (delegates) |

**Separation of concerns:**
- Pool service: "what to show" (visibility)
- FSM: "what transitions are valid" (business rules)
- RBAC: "who can do what" (authorization)

---

### 10. Testing Strategy

#### A. Domain Pool Tests
```python
def test_available_guarantees_no_blockers(db):
    """available status guarantees dependencies resolved."""
    pred = _make_task(db, status=TaskStatus.in_progress)
    succ = _make_task(db, status=TaskStatus.blocked)
    _add_dependency(db, pred.id, succ.id)
    
    # try to transition to available (should fail)
    result = try_transition_to_available(succ, db)
    
    assert result == False
    assert succ.status == TaskStatus.blocked.value
    
    # complete predecessor
    pred.status = TaskStatus.done.value
    db.commit()
    
    # now can transition
    result = try_transition_to_available(succ, db)
    
    assert result == True
    assert succ.status == TaskStatus.available.value
```

#### B. Access Projection Tests
```python
def test_low_skill_executor_sees_empty_pool(db):
    """Executor below MIN_SKILL_TO_TAKE sees no tasks."""
    task = _make_task(db, status=TaskStatus.available)
    
    low_skill_actor = Actor(
        role="executor",
        skill_level=1,  # < MIN_SKILL_TO_TAKE
        specializations={Trade.electrician},
    )
    
    service = TaskPoolService(db)
    projection = service.get_pool_projection(
        org_id=task.org_id,
        project_id=task.project_id,
        actor=low_skill_actor,
    )
    
    assert len(projection) == 0
```

#### C. Race Condition Tests
```python
def test_concurrent_self_assign_only_one_succeeds(db):
    """Only one executor can assign same task."""
    task = _make_task(db, status=TaskStatus.available, row_version=1)
    
    executor_a = uuid4()
    executor_b = uuid4()
    
    # both try to assign simultaneously
    result_a = self_assign(task, executor_a, expected_row_version=1, db)
    
    with pytest.raises(VersionConflict):
        self_assign(task, executor_b, expected_row_version=1, db)
    
    # only A got the task
    assert task.assigned_to == executor_a
    assert task.row_version == 2
```

---

### 11. Migration Path (Existing → Golden Standard)

If you have existing tasks:

1. Add new statuses to enum (`blocked`, `planned`)
2. Create migration to set initial statuses:
```sql
-- Classify existing tasks
UPDATE tasks SET status = 'blocked'
WHERE status = 'new' 
  AND EXISTS (
    SELECT 1 FROM task_dependencies d
    JOIN tasks t ON t.id = d.predecessor_id
    WHERE d.successor_id = tasks.id
      AND t.status <> 'done'
  );

UPDATE tasks SET status = 'available'
WHERE status = 'new'
  AND assigned_to IS NULL
  AND status NOT IN ('blocked', 'done', 'canceled');
```
3. Deploy event-driven logic (`on_task_completed`)
4. Run safety net job once to reconcile
5. Monitor for stuck tasks

---

### Summary: Golden Standard Guarantees

✅ **Domain pool** = `status == 'available'` (single source of truth)  
✅ **`available`** = preconditions met (not filter result)  
✅ **Access projection** respects role + skill + trade  
✅ **Single SQL query** for pool (no N+1, honest pagination)  
✅ **Event-driven updates** + optional safety net  
✅ **Race protection** via optimistic locking  
✅ **Clean architecture** (model → service → API)

---

**Status:** Ready for implementation  
**Next:** `TaskPoolService` + `on_task_completed` + indexes

---
# Status Model (updated: remove `planned`)
Statuses related to pool:

- blocked : has unresolved dependencies OR business holds

- available : ready to be picked by executor (TASK POOL)

- assigned : has primary executor for current shift

- in_progress : work started

- submitted : work completed, awaiting QC

- done : terminal

- canceled : terminal



### Core transitions

blocked → available : when last dependency is resolved AND no business holds

available → assigned : executor self-assigns OR lead assigns

assigned → in_progress : owner starts work

in_progress → submitted : owner submits for QC

submitted → done : QC approve OR self-QC approve (if allowed)

submitted → in_progress : QC reject

## Business holds (clarification)

Business holds are conditions that prevent a task from being `available`, even if dependencies are satisfied.

Typical holds:
- materials / tools not available
- resource contention / intersection with other tasks (work area conflict, race conditions)
- manual stop by lead/supervisor

Executor cannot unilaterally "drop" an in-progress task back to the pool.
To stop work due to a hold, executor uses `escalate` and lead/supervisor decides:
- add helper(s)
- pause via hold
- recall to pool (`recall_to_pool`)
- reassign owner


## Controlled return to pool (final)

Return to pool from `in_progress` is allowed only via:
- `shift_release` (system, end of shift)
- `recall_to_pool` (lead/supervisor, forced recall / reassignment)

Executor cannot return a task to the pool from `in_progress`.

Executor can complete work only by:
- `submit` (normal completion path)
- waiting for `shift_release`
- escalating to lead (`escalate`) and acting on lead's decision

## Responsibility rule (submit ownership)

Responsibility for task outcome is associated with the owner who performs `submit`.

If ownership changes during execution, the final submitter is the accountable owner for the submitted result.

## Shift semantics (updated)

At end of shift, system performs `shift_release`:

- clears primary owner
- clears active contributors
- transitions task back to `available` directly (no intermediate status),
  provided domain invariants still hold

Shift release is one of the only two allowed ways to return `in_progress` tasks to the pool.

## Fix flow (updated: allow from `submitted` and `done`)

Fix is an explicit correction workflow and is created as a separate task.

Rules:
- fix can be created from `submitted` (defect found during review)
- fix can also be created from `done` (late defect found after completion)
- fix is initiated by lead/supervisor
- fix task references original task via `fix_of_task_id`
- every fix must be associated with a defect record (reason + what_to_fix + how_fixed)

## Actor specializations header contract (MVP)

For MVP, actor specializations are provided as a JSON-like array of strings in request context (e.g., header or claim).

Example (conceptual):
- `["electrician","mechanic"]`

The backend treats specializations as a set for projection filtering.


---
# Golden Standard: Task Pool & Execution Architecture

---

## Core Principle

```
Domain pool = Task.status == 'available' (single source of truth)

'available' is a GUARANTEE, not a filter result.
```

Статус `available` означает, что задача **полностью готова** к взятию в работу.
Пул задач определяется **только** этим статусом и ничем другим.

---

## 1. Status Model (final)

```
Statuses related to execution:

- blocked      : has unresolved dependencies OR business holds
- available    : ready to be picked by executor (TASK POOL)
- assigned     : has primary executor for current shift
- in_progress  : work started
- submitted    : work completed, awaiting QC
- done         : terminal
- canceled     : terminal
```