# tests/test_db_invariants_m5_org_safe_fks.py
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy.exc import IntegrityError

from tests.factories import (
    make_project_template,
    make_task,
    make_allocation,
)


def test_db_fk_task_allocations_org_safe(db):
    """
    task_allocations.org_id обязан совпадать с tasks.org_id
    """
    org_id = uuid.uuid4()
    other_org_id = uuid.uuid4()
    created_by = uuid.uuid4()
    user_id = uuid.uuid4()

    pt = make_project_template(db, org_id=org_id)

    task = make_task(
        db,
        org_id=org_id,
        project_id=pt.project_id,
        created_by=created_by,
        status="assigned",
        assigned_to=user_id,
        assigned_at=datetime.now(tz=timezone.utc),  # ✅ обязательное поле
    )
    db.commit()

    # корректная аллокация
    make_allocation(
        db,
        org_id=org_id,
        task_id=task.id,
        user_id=user_id,
    )
    db.commit()

    # аллокация с другим org_id — должна упасть
    with pytest.raises(IntegrityError):
        make_allocation(
            db,
            org_id=other_org_id,
            task_id=task.id,
            user_id=user_id,
            flush=True,
        )


def test_db_fk_task_allocations_task_fk(db):
    """
    task_allocations.task_id обязан существовать
    """
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with pytest.raises(IntegrityError):
        make_allocation(
            db,
            org_id=org_id,
            task_id=uuid.uuid4(),  # несуществующая задача
            user_id=user_id,
            flush=True,
        )
