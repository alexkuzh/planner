from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_allocation import TaskAllocation


class TaskAllocationService:
    def __init__(self, db: Session):
        self.db = db

    def create_batch(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        work_date: date,
        shift_code: str,
        allocated_by: UUID,
        allocations: list[dict],  # [{"task_id": UUID, "allocated_to": UUID, "note": str|None}]
    ) -> list[TaskAllocation]:
        created: list[TaskAllocation] = []

        for item in allocations:
            task_id: UUID = item["task_id"]
            allocated_to: UUID = item["allocated_to"]
            note = item.get("note")

            task: Task | None = self.db.get(Task, task_id)
            if task is None:
                raise ValueError(f"Task not found: {task_id}")

            # базовый guard: нельзя распределять задачу из другого org/project
            if task.org_id != org_id or task.project_id != project_id:
                raise ValueError("Task org_id/project_id mismatch for allocation")

            # базовый guard: нет смысла распределять done/canceled
            if task.status in ("done", "canceled"):
                raise ValueError(f"Task is not allocatable in status: {task.status}")

            alloc = TaskAllocation(
                org_id=org_id,
                project_id=project_id,
                task_id=task.id,
                work_date=work_date,
                shift_code=shift_code,
                allocated_to=allocated_to,
                allocated_by=allocated_by,
                note=note,
            )

            self.db.add(alloc)
            created.append(alloc)

        self.db.commit()
        return created

    def list_for_shift(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        work_date: date,
        shift_code: str,
    ) -> list[TaskAllocation]:
        return (
            self.db.query(TaskAllocation)
            .filter(
                TaskAllocation.org_id == org_id,
                TaskAllocation.project_id == project_id,
                TaskAllocation.work_date == work_date,
                TaskAllocation.shift_code == shift_code,
            )
            .order_by(TaskAllocation.created_at.desc())
            .all()
        )

    def list_for_user(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        work_date: date,
        user_id: UUID,
    ) -> list[TaskAllocation]:
        return (
            self.db.query(TaskAllocation)
            .filter(
                TaskAllocation.org_id == org_id,
                TaskAllocation.project_id == project_id,
                TaskAllocation.work_date == work_date,
                TaskAllocation.allocated_to == user_id,
            )
            .order_by(TaskAllocation.created_at.desc())
            .all()
        )
