from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.db import get_db

from app.models.deliverable import Deliverable, DeliverableStatus
from app.models.deliverable_signoff import DeliverableSignoff,SignoffResult
from app.models.qc_inspection import QcInspection, QcResult
from app.models.task import Task, TaskStatus, TaskKind

from app.schemas.deliverable import DeliverableCreate, DeliverableRead
from app.schemas.deliverable_signoff import DeliverableSignoffCreate, DeliverableSignoffRead
from app.schemas.deliverable_actions import SubmitToQcRequest
from app.schemas.deliverable_dashboard import DeliverableDashboard
from app.schemas.qc_inspection import QcDecisionRequest, QcInspectionRead
from app.schemas.task import TaskRead


router = APIRouter(prefix="/deliverables", tags=["deliverables"])


@router.post("", response_model=DeliverableRead, status_code=status.HTTP_201_CREATED)
def create_deliverable(data: DeliverableCreate, db: Session = Depends(get_db)):
    # Проверим уникальность serial в org (чтобы вернуть 409, а не 500)
    existing = db.execute(
        select(Deliverable).where(
            Deliverable.org_id == data.org_id,
            Deliverable.serial == data.serial,
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Deliverable with this serial already exists in org")

    d = Deliverable(
        org_id=data.org_id,
        project_id=data.project_id,
        deliverable_type=data.deliverable_type,
        serial=data.serial,
        status=DeliverableStatus.open.value,
        created_by=data.created_by,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.get("/{deliverable_id}", response_model=DeliverableRead)
def get_deliverable(deliverable_id: UUID, db: Session = Depends(get_db)):
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return d


@router.get("", response_model=list[DeliverableRead])
def list_deliverables(org_id: UUID, project_id: UUID, db: Session = Depends(get_db)):
    return (
        db.query(Deliverable)
        .filter(Deliverable.org_id == org_id, Deliverable.project_id == project_id)
        .order_by(Deliverable.created_at.desc())
        .all()
    )


@router.post("/{deliverable_id}/signoffs", response_model=DeliverableSignoffRead, status_code=status.HTTP_201_CREATED)
def create_signoff(deliverable_id: UUID, body: DeliverableSignoffCreate, db: Session = Depends(get_db)):
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    if d.org_id != body.org_id or d.project_id != body.project_id:
        raise HTTPException(status_code=422, detail="org_id/project_id mismatch")

    s = DeliverableSignoff(
        org_id=body.org_id,
        project_id=body.project_id,
        deliverable_id=deliverable_id,
        signed_off_by=body.signed_off_by,
        result=body.result.value if hasattr(body.result, "value") else str(body.result),
        comment=body.comment,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/{deliverable_id}/signoffs", response_model=list[DeliverableSignoffRead])
def list_signoffs(deliverable_id: UUID, org_id: UUID, db: Session = Depends(get_db)):
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    if d.org_id != org_id:
        raise HTTPException(status_code=422, detail="org_id mismatch")

    return (
        db.query(DeliverableSignoff)
        .filter(DeliverableSignoff.deliverable_id == deliverable_id)
        .order_by(DeliverableSignoff.created_at.asc())
        .all()
    )


@router.post("/{deliverable_id}/submit_to_qc", response_model=DeliverableRead)
def submit_to_qc(deliverable_id: UUID, body: SubmitToQcRequest, db: Session = Depends(get_db)):
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    if d.org_id != body.org_id or d.project_id != body.project_id:
        raise HTTPException(status_code=422, detail="org_id/project_id mismatch")

    if d.status not in (DeliverableStatus.open.value, DeliverableStatus.qc_rejected.value):
        raise HTTPException(status_code=422, detail=f"Submit to QC not allowed from status '{d.status}'")

    # берём самый свежий signoff
    last_signoff = (
        db.query(DeliverableSignoff)
        .filter(DeliverableSignoff.deliverable_id == deliverable_id)
        .order_by(DeliverableSignoff.created_at.desc())
        .first()
    )
    if not last_signoff:
        raise HTTPException(status_code=422, detail="Cannot submit to QC without production sign-off")

    if last_signoff.result != SignoffResult.approved.value:
        raise HTTPException(status_code=422, detail="Last production sign-off is not approved")

    d.status = DeliverableStatus.submitted_to_qc.value
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.get("/{deliverable_id}/qc_inspections", response_model=list[QcInspectionRead])
def list_qc_inspections(deliverable_id: UUID, org_id: UUID, db: Session = Depends(get_db)):
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    if d.org_id != org_id:
        raise HTTPException(status_code=422, detail="org_id mismatch")

    return (
        db.query(QcInspection)
        .filter(QcInspection.deliverable_id == deliverable_id)
        .order_by(QcInspection.created_at.asc())
        .all()
    )


@router.post("/{deliverable_id}/qc_decision", response_model=DeliverableRead)
def qc_decision(deliverable_id: UUID, body: QcDecisionRequest, db: Session = Depends(get_db)):
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    if d.org_id != body.org_id or d.project_id != body.project_id:
        raise HTTPException(status_code=422, detail="org_id/project_id mismatch")

    if d.status != DeliverableStatus.submitted_to_qc.value:
        raise HTTPException(status_code=422, detail=f"QC decision not allowed from status '{d.status}'")

    responsible_user_id = None
    if body.result == QcResult.rejected:
        last_approved_signoff = (
            db.query(DeliverableSignoff)
            .filter(
                DeliverableSignoff.deliverable_id == deliverable_id,
                DeliverableSignoff.result == SignoffResult.approved.value,
            )
            .order_by(DeliverableSignoff.created_at.desc())
            .first()
        )
        if last_approved_signoff:
            responsible_user_id = last_approved_signoff.signed_off_by


    # записываем факт инспекции
    qc = QcInspection(
        org_id=body.org_id,
        project_id=body.project_id,
        deliverable_id=deliverable_id,
        inspector_user_id=body.inspector_user_id,
        responsible_user_id=responsible_user_id,
        result=body.result.value if hasattr(body.result, "value") else str(body.result),
        notes=body.notes,
    )
    db.add(qc)

    if body.result == QcResult.approved:
        d.status = DeliverableStatus.qc_approved.value
    else:
        d.status = DeliverableStatus.qc_rejected.value

        # создаём "исправление (QC)" task, привязанный к этому изделию
        fix_title = f"Исправление (QC): {d.deliverable_type} {d.serial}"
        if body.notes:
            # чтобы заголовок не разрастался
            fix_title = fix_title[:250]

        fix_task = Task(
            org_id=d.org_id,
            project_id=d.project_id,
            created_by=body.inspector_user_id,  # в MVP: кто создал — QC инспектор
            title=fix_title,
            description=body.notes,
            priority=0,
            status=TaskStatus.new.value,
            kind=TaskKind.production.value,
            other_kind_label=None,
            deliverable_id=d.id,
            parent_task_id=None,   # тут можно потом связать с исходной task, если понадобится
            fix_reason="QC rejected",
        )
        db.add(fix_task)

    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.get("/{deliverable_id}/tasks", response_model=list[TaskRead])
def list_deliverable_tasks(deliverable_id: UUID, org_id: UUID, db: Session = Depends(get_db)):
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    if d.org_id != org_id:
        raise HTTPException(status_code=422, detail="org_id mismatch")

    return (
        db.query(Task)
        .filter(Task.deliverable_id == deliverable_id)
        .order_by(Task.created_at.asc())
        .all()
    )


@router.get("/{deliverable_id}/dashboard", response_model=DeliverableDashboard)
def get_dashboard(deliverable_id: UUID, org_id: UUID, db: Session = Depends(get_db)):
    d = db.get(Deliverable, deliverable_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    if d.org_id != org_id:
        raise HTTPException(status_code=422, detail="org_id mismatch")

    tasks = (
        db.query(Task)
        .filter(Task.deliverable_id == deliverable_id)
        .order_by(Task.created_at.asc())
        .all()
    )

    last_signoff = (
        db.query(DeliverableSignoff)
        .filter(DeliverableSignoff.deliverable_id == deliverable_id)
        .order_by(DeliverableSignoff.created_at.desc())
        .first()
    )

    last_qc = (
        db.query(QcInspection)
        .filter(QcInspection.deliverable_id == deliverable_id)
        .order_by(QcInspection.created_at.desc())
        .first()
    )

    return DeliverableDashboard(
        deliverable=d,
        tasks=tasks,
        last_signoff=last_signoff,
        last_qc_inspection=last_qc,
    )
