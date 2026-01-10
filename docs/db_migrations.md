# DB migrations playbook (PostgreSQL)

_Updated: 2026-01-10 19:47:29Z_

Цель: усиливать БД (целостность/индексы) **без усложнения кода** и без опасных блокировок в проде.

---

## Принципы

### Что держим в БД
- **Referential integrity**: FK (включая композитные `org_id`-aware ссылки).
- **Идемпотентность на записи событий/переходов**:  
  `UNIQUE (org_id, client_event_id) WHERE client_event_id IS NOT NULL`.
- **Простые CHECK-инварианты**, которые не завязаны на FSM:
  - `row_version >= 1`
  - `assigned_to IS NULL <-> assigned_at IS NULL`
  - `minutes_spent IS NULL OR minutes_spent >= 0`
  - анти-“нулевой UUID” для ключевых uuid-полей (если применимо)
- **Индексы под реальные запросы**, после того, как видим паттерны выборок (код/EXPLAIN/статистика).

### Что НЕ тащим в БД
- FSM-правила: допустимые переходы, условия reject/fix и т.п.
- Сложные бизнес-инварианты, требующие чтения нескольких таблиц/строк (это сервис).
- Триггеры ради “умной логики” (исключение — редкие случаи, обсуждаются отдельно).

---

## Стратегия `NOT VALID` → `VALIDATE` (для прод обязательно)

### Почему
- `ADD CONSTRAINT ... NOT VALID` добавляет ограничение **без полной проверки всей таблицы**.
- `VALIDATE CONSTRAINT` проверяет исторические данные позже и обычно требует меньше блокировок, чем “валидировать сразу”.
- Это позволяет делать миграции **без простоя** и отдельными, контролируемыми шагами.

---

## Шаблоны миграций

### 1) Добавление FK (org-aware) безопасно

#### Шаг A — добавили FK как `NOT VALID`
```sql
ALTER TABLE child
  ADD CONSTRAINT fk_child_parent_org
  FOREIGN KEY (org_id, parent_id)
  REFERENCES parent (org_id, id)
  ON DELETE CASCADE
  NOT VALID;
```

#### Шаг B — диагностика данных (до VALIDATE)
**Cross-org** (ссылка ведёт на другую организацию):
```sql
SELECT count(*) AS bad_links
FROM child c
JOIN parent p ON p.id = c.parent_id
WHERE c.org_id <> p.org_id;
```

**Missing** (ссылка ведёт в никуда):
```sql
SELECT count(*) AS missing_links
FROM child c
LEFT JOIN parent p ON p.id = c.parent_id
WHERE p.id IS NULL;
```

#### Шаг C — backfill / cleanup (если нужно)
Всегда отдельным шагом/миграцией. Пример: вставка “справочника” под существующие ссылки.

```sql
INSERT INTO project_templates (id, org_id, project_id, created_at, updated_at)
SELECT gen_random_uuid(), t.org_id, t.project_id, now(), now()
FROM (SELECT DISTINCT org_id, project_id FROM tasks) t
LEFT JOIN project_templates p ON p.project_id = t.project_id
WHERE p.project_id IS NULL;
```

#### Шаг D — `VALIDATE`
```sql
ALTER TABLE child VALIDATE CONSTRAINT fk_child_parent_org;
```

---

### 2) Добавление CHECK безопасно

#### Шаг A — `NOT VALID`
```sql
ALTER TABLE tasks
  ADD CONSTRAINT ck_tasks_row_version_ge_1
  CHECK (row_version >= 1)
  NOT VALID;
```

#### Шаг B — диагностика
```sql
SELECT count(*) AS bad_rows
FROM tasks
WHERE row_version < 1;
```

#### Шаг C — `VALIDATE`
```sql
ALTER TABLE tasks VALIDATE CONSTRAINT ck_tasks_row_version_ge_1;
```

---

## Индексы: только `CONCURRENTLY` (в проде)

### Правило
В проде используем только:
```sql
CREATE INDEX CONCURRENTLY ...
```

### Почему
Обычный `CREATE INDEX` берёт блокировки, мешающие записи. `CONCURRENTLY` дольше, но безопаснее для работающего сервиса.

### Примеры (из нашего домена)

#### Индекс под очередь исполнителя
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tasks_org_assigned_status_assignedat
ON tasks (org_id, assigned_to, status, assigned_at DESC)
WHERE assigned_to IS NOT NULL;
```

#### Индекс под быстрый фильтр по статусу в org
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tasks_org_status
ON tasks (org_id, status);
```

#### Индекс под события по задаче (WHERE task_id + ORDER BY id)
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_task_events_task_id_id
ON task_events (task_id, id);
```

#### Индекс под задачи изделия (WHERE deliverable_id + ORDER BY created_at)
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tasks_deliverable_created_at
ON tasks (deliverable_id, created_at);
```

---

## Разбиение миграций (рекомендуемый порядок)

Часто лучше делать 2–3 миграции вместо одной:

1) **Constraints `NOT VALID`**
2) **Backfill / cleanup** (если нужен)
3) **`VALIDATE`**  
   Индексы `CONCURRENTLY` — отдельной миграцией/шагом (часто в autocommit).

---

## Checklist перед merge миграции

1) Есть ли “org-aware” FK там, где есть `org_id`?
2) Новый FK/CK добавлен `NOT VALID`, а `VALIDATE` вынесен отдельно?
3) Перед `VALIDATE` есть диагностические запросы “bad links / missing links”?
4) Индексы создаются `CONCURRENTLY`?
5) Индексы соответствуют реальным запросам (код/EXPLAIN), а не “на всякий случай”?
6) FSM-логика не уехала в БД?

---

## DB vs Service boundary (что не тащить в БД)

### Оставляем в сервисе (не в БД)
- FSM: допустимые переходы, требования к payload (`assign_to`, `fix_reason` и т.п.)
- Правила “done запрещён при blockers/зависимостях/незакрытых дочерних”
- Автосоздание `fix-task` и вся логика QC/reject loop
- Межтабличные бизнес-инварианты и “умные” триггеры
- Валидация структуры JSONB payload и его эволюция

### Оставляем в БД (DB first)
- org-aware FK (структурная целостность)
- идемпотентность (`UNIQUE (org_id, client_event_id) WHERE ...`)
- простые CHECK-инварианты в пределах строки
- индексы под реальные запросы (`CONCURRENTLY` в проде)
MD



## Мини-памятка по psql

- Выйти из `psql`: `\q`
- Прервать текущий ввод: `Ctrl+C`
