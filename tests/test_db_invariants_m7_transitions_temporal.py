import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _setup_project_and_task(db: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """
    Создаёт:
      - project_templates row (чтобы прошёл FK tasks.project_id)
      - tasks row (минимально валидный под ваши CHECK)
    Возвращает (org_id, project_id, task_id).
    """
    org_id = _uuid()
    project_id = _uuid()
    task_id = _uuid()

    # project_templates: минимум полей по вашей M6-практике
    db.execute(
        text(
            """
            INSERT INTO project_templates (id, org_id, project_id, active_template_version_id, updated_by)
            VALUES (:id, :org_id, :project_id, NULL, NULL)
            """
        ),
        {"id": _uuid(), "org_id": org_id, "project_id": project_id},
    )

    # tasks: status=available => assigned_to/assigned_at MUST be NULL
    db.execute(
        text(
            """
            INSERT INTO tasks (id, org_id, project_id, title, kind, status, created_by)
            VALUES (:id, :org_id, :project_id, :title, :kind, :status, :created_by)
            """
        ),
        {
            "id": task_id,
            "org_id": org_id,
            "project_id": project_id,
            "title": "Task",
            "kind": "production",
            "status": "available",
            "created_by": _uuid(),
        },
    )

    return org_id, project_id, task_id


def test_m7_transition_result_rv_must_equal_expected_plus_one(db: Session):
    org_id, project_id, task_id = _setup_project_and_task(db)

    # expected=1 => result MUST be 2, но мы вставляем 3 => IntegrityError
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    """
                    INSERT INTO task_transitions (
                        id, org_id, project_id, task_id,
                        from_status, to_status, action,
                        payload, actor_user_id,
                        expected_row_version, result_row_version
                    )
                    VALUES (
                        :id, :org_id, :project_id, :task_id,
                        :from_status, :to_status, :action,
                        CAST(:payload AS jsonb), :actor_user_id,
                        :expected_row_version, :result_row_version
                    )
                    """
                ),
                {
                    "id": _uuid(),
                    "org_id": org_id,
                    "project_id": project_id,
                    "task_id": task_id,
                    "from_status": "available",
                    "to_status": "assigned",
                    "action": "assign",
                    "payload": "{}",
                    "actor_user_id": _uuid(),
                    "expected_row_version": 1,
                    "result_row_version": 3,  # ❌ должно быть 2
                },
            )


def test_m7_transition_result_rv_unique_per_task(db: Session):
    org_id, project_id, task_id = _setup_project_and_task(db)

    # 1-й transition ok: expected=1 => result=2
    db.execute(
        text(
            """
            INSERT INTO task_transitions (
                id, org_id, project_id, task_id,
                from_status, to_status, action,
                payload, actor_user_id,
                expected_row_version, result_row_version
            )
            VALUES (
                :id, :org_id, :project_id, :task_id,
                :from_status, :to_status, :action,
                CAST(:payload AS jsonb), :actor_user_id,
                :expected_row_version, :result_row_version
            )
            """
        ),
        {
            "id": _uuid(),
            "org_id": org_id,
            "project_id": project_id,
            "task_id": task_id,
            "from_status": "available",
            "to_status": "assigned",
            "action": "assign",
            "payload": "{}",
            "actor_user_id": _uuid(),
            "expected_row_version": 1,
            "result_row_version": 2,
        },
    )

    # 2-й transition с тем же result_row_version=2 должен упасть на UNIQUE
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    """
                    INSERT INTO task_transitions (
                        id, org_id, project_id, task_id,
                        from_status, to_status, action,
                        payload, actor_user_id,
                        expected_row_version, result_row_version
                    )
                    VALUES (
                        :id, :org_id, :project_id, :task_id,
                        :from_status, :to_status, :action,
                        CAST(:payload AS jsonb), :actor_user_id,
                        :expected_row_version, :result_row_version
                    )
                    """
                ),
                {
                    "id": _uuid(),
                    "org_id": org_id,
                    "project_id": project_id,
                    "task_id": task_id,
                    "from_status": "available",
                    "to_status": "in_progress",
                    "action": "start",
                    "payload": "{}",
                    "actor_user_id": _uuid(),
                    "expected_row_version": 1,
                    "result_row_version": 2,  # ❌ дубль
                },
            )


def test_m7_transition_result_row_version_not_null(db: Session):
    org_id, project_id, task_id = _setup_project_and_task(db)

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    """
                    INSERT INTO task_transitions (
                        id, org_id, project_id, task_id,
                        from_status, to_status, action,
                        payload, actor_user_id,
                        expected_row_version, result_row_version
                    )
                    VALUES (
                        :id, :org_id, :project_id, :task_id,
                        :from_status, :to_status, :action,
                        CAST(:payload AS jsonb), :actor_user_id,
                        :expected_row_version, :result_row_version
                    )
                    """
                ),
                {
                    "id": _uuid(),
                    "org_id": org_id,
                    "project_id": project_id,
                    "task_id": task_id,
                    "from_status": "available",
                    "to_status": "assigned",
                    "action": "assign",
                    "payload": "{}",
                    "actor_user_id": _uuid(),
                    "expected_row_version": 1,
                    "result_row_version": None,  # ❌ NOT NULL
                },
            )
