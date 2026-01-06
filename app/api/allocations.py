# app/api/allocations.py

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.allocation import AllocationBatchRequest, AllocationOut
from app.services.task_allocation_service import TaskAllocationService
from app.api.deps import get_current_user_id
from app.models.task import Task
from app.models.deliverable import Deliverable



router = APIRouter(prefix="/allocations", tags=["allocations"])


@router.post("/batch", response_model=list[AllocationOut])
def create_batch(
    req: AllocationBatchRequest,
    db: Session = Depends(get_db),
    actor_user_id: UUID = Depends(get_current_user_id),
):
    service = TaskAllocationService(db)

    try:
        rows = service.create_batch(
            org_id=req.org_id,
            project_id=req.project_id,
            work_date=req.work_date,
            shift_code=req.shift_code,
            allocated_by=actor_user_id,
            allocations=[a.model_dump() for a in req.allocations],
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return [
        AllocationOut(
            id=r.id,
            org_id=r.org_id,
            project_id=r.project_id,
            task_id=r.task_id,
            work_date=r.work_date,
            shift_code=r.shift_code,
            allocated_to=r.allocated_to,
            allocated_by=r.allocated_by,
            note=r.note,
        )
        for r in rows
    ]


@router.get("/today", response_model=list[AllocationOut])
def list_for_shift(
    org_id: UUID = Query(...),
    project_id: UUID = Query(...),
    work_date: date = Query(...),
    shift_code: str = Query(..., pattern="^(begin_of_week|end_of_week)$"),
    db: Session = Depends(get_db),
    actor_user_id: UUID = Depends(get_current_user_id),
):
    service = TaskAllocationService(db)

    rows = service.list_for_shift(
        org_id=org_id,
        project_id=project_id,
        work_date=work_date,
        shift_code=shift_code,
    )
    # --- batch load tasks ---
    task_ids = [r.task_id for r in rows]
    tasks = (
        db.query(Task)
        .filter(Task.id.in_(task_ids))
        .all()
    )
    task_by_id = {t.id: t for t in tasks}

    # --- batch load deliverables ---
    deliverable_ids = [t.deliverable_id for t in tasks if t.deliverable_id is not None]
    deliverables = []
    if deliverable_ids:
        deliverables = (
            db.query(Deliverable)
            .filter(Deliverable.id.in_(deliverable_ids))
            .all()
        )
    deliverable_by_id = {d.id: d for d in deliverables}

    out: list[AllocationOut] = []
    for r in rows:
        t = task_by_id.get(r.task_id)
        deliverable_id = t.deliverable_id if t else None
        d = deliverable_by_id.get(deliverable_id) if deliverable_id else None

        out.append(
            AllocationOut(
                id=r.id,
                org_id=r.org_id,
                project_id=r.project_id,
                task_id=r.task_id,
                work_date=r.work_date,
                shift_code=r.shift_code,
                allocated_to=r.allocated_to,
                allocated_by=r.allocated_by,
                note=r.note,

                deliverable_id=deliverable_id,
                deliverable_type=d.deliverable_type if d else None,
                deliverable_serial=d.serial if d else None,
            )
        )
    return out


@router.get("/my", response_model=list[AllocationOut])
def list_my(
    org_id: UUID = Query(...),
    project_id: UUID = Query(...),
    work_date: date = Query(...),
    db: Session = Depends(get_db),
    actor_user_id: UUID = Depends(get_current_user_id),
):
    service = TaskAllocationService(db)

    rows = service.list_for_user(
        org_id=org_id,
        project_id=project_id,
        work_date=work_date,
        user_id=actor_user_id,
    )
    # --- batch load tasks ---
    task_ids = [r.task_id for r in rows]
    tasks = (
        db.query(Task)
        .filter(Task.id.in_(task_ids))
        .all()
    )
    task_by_id = {t.id: t for t in tasks}

    # --- batch load deliverables ---
    deliverable_ids = [t.deliverable_id for t in tasks if t.deliverable_id is not None]
    deliverables = []
    if deliverable_ids:
        deliverables = (
            db.query(Deliverable)
            .filter(Deliverable.id.in_(deliverable_ids))
            .all()
        )
    deliverable_by_id = {d.id: d for d in deliverables}

    out: list[AllocationOut] = []
    for r in rows:
        t = task_by_id.get(r.task_id)
        deliverable_id = t.deliverable_id if t else None
        d = deliverable_by_id.get(deliverable_id) if deliverable_id else None

        out.append(
            AllocationOut(
                id=r.id,
                org_id=r.org_id,
                project_id=r.project_id,
                task_id=r.task_id,
                work_date=r.work_date,
                shift_code=r.shift_code,
                allocated_to=r.allocated_to,
                allocated_by=r.allocated_by,
                note=r.note,

                deliverable_id=deliverable_id,
                deliverable_type=d.deliverable_type if d else None,
                deliverable_serial=d.serial if d else None,
            )
        )
    return out

