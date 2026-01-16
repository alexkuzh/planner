# app/api/deliverables.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Body, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID

from pydantic import BaseModel

from app.core.db import get_db

from app.models.deliverable import Deliverable, DeliverableStatus
from app.models.deliverable_signoff import DeliverableSignoff, SignoffResult
from app.models.qc_inspection import QcInspection, QcResult
from app.models.task import Task, FixSeverity

from app.api.deps import get_actor_role
from app.core.rbac import ensure_allowed, Forbidden

from app.schemas.deliverable import DeliverableCreate, DeliverableRead
from app.schemas.deliverable_signoff import DeliverableSignoffCreate, DeliverableSignoffRead
from app.schemas.deliverable_actions import SubmitToQcRequest, DeliverableBootstrapRequest
from app.schemas.deliverable_dashboard import DeliverableDashboard
from app.schemas.qc_inspection import QcDecisionRequest, QcInspectionRead
from app.schemas.task import TaskRead
from app.schemas.command import Command
from app.schemas.fix_task import DeliverableFixPayload

from app.services.task_fix_service import TaskFixService
from app.services.deliverable_bootstrap_service import DeliverableBootstrapService, BootstrapError


router = APIRouter(prefix="/deliverables", tags=["deliverables"])

DELIVERABLE_FIX_OPENAPI_EXAMPLES = {
    "worker_initiative": {
        "summary": "Create deliverable fix-task (worker initiative)",
        "description": "Исправление по инициативе работника на уровне deliverable (без origin_task).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "expected_row_version": 1,
            "client_event_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "payload": {
                "title": "Инициативный фикс",
                "description": "Нашел косяк по месту — исправил.",
                "severity": "minor",
                "minutes_spent": 15,
                "attachments": []
            }
        },
    }
}

QC_DECISION_OPENAPI_EXAMPLES = {
    "approve": {
        "summary": "QC approve deliverable",
        "description": "QC подтверждает изделие. notes опционально.",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "project_id": "22222222-2222-2222-2222-222222222222",
            "inspector_user_id": "33333333-3333-3333-3333-333333333333",
            "result": "approved",
            "notes": "OK",
        },
    },
    "reject": {
        "summary": "QC reject deliverable",
        "description": "QC отклоняет изделие. notes обязательно (причина/замечания).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "project_id": "22222222-2222-2222-2222-222222222222",
            "inspector_user_id": "33333333-3333-3333-3333-333333333333",
            "result": "rejected",
            "notes": "Царапина на корпусе, требуется исправление",
        },
    },
}

SUBMIT_TO_QC_OPENAPI_EXAMPLES = {
    "submit": {
        "summary": "Submit deliverable to QC",
        "description": "Отправить изделие в QC. Требуется последний production sign-off со статусом approved.",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "project_id": "22222222-2222-2222-2222-222222222222",
            "actor_user_id": "33333333-3333-3333-3333-333333333333"
        }
    }
}

SIGNOFF_OPENAPI_EXAMPLES = {
    "approve": {
        "summary": "Production sign-off (approve)",
        "description": "Подтверждение, что все задачи по изделию выполнены.",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "project_id": "22222222-2222-2222-2222-222222222222",
            "signed_off_by": "33333333-3333-3333-3333-333333333333",
            "result": "approved",
            "comment": "Все задачи выполнены, изделие готово к QC"
        },
    },
    "reject": {
        "summary": "Production sign-off (reject)",
        "description": "Отклонение sign-off (редкий случай).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "project_id": "22222222-2222-2222-2222-222222222222",
            "signed_off_by": "33333333-3333-3333-3333-333333333333",
            "result": "rejected",
            "comment": "Не все задачи выполнены"
        },
    },
}

DELIVERABLE_CREATE_OPENAPI_EXAMPLES = {
    "basic": {
        "summary": "Create deliverable",
        "description": "Создать изделие (serial приходит извне).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "project_id": "22222222-2222-2222-2222-222222222222",
            "created_by": "33333333-3333-3333-3333-333333333333",
            "deliverable_type": "box_v1",
            "serial": "SN-2026-0001",
        },
    },
}

DELIVERABLE_BOOTSTRAP_OPENAPI_EXAMPLES = {
    "basic": {
        "summary": "Bootstrap deliverable",
        "description": "Развернуть дерево задач по активной версии шаблона проекта.",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "project_id": "22222222-2222-2222-2222-222222222222",
        },
    }
}

class DeliverableBootstrapResponse(BaseModel):
    template_version_id: UUID
    created_tasks: int
    created_dependencies: int


@router.post("", response_model=DeliverableRead, status_code=status.HTTP_201_CREATED)
def create_deliverable(
        data: DeliverableCreate = Body(..., openapi_examples=DELIVERABLE_CREATE_OPENAPI_EXAMPLES),
        db: Session = Depends(get_db),
    ):
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


@router.post(    "/{deliverable_id}/signoffs",
        response_model=DeliverableSignoffRead,
        status_code=status.HTTP_201_CREATED,
        summary="Create production sign-off for deliverable",
        description=(
            "Production sign-off — точка ответственности перед отправкой в QC.\n\n"
            "QC reject определяет responsible_user_id как `last approved signoff.signed_off_by`.\n"
            "Используйте sign-off перед `submit_to_qc` (MVP gate требует approved sign-off)."
            ),
        )
def create_signoff(
    deliverable_id: UUID,
    body: DeliverableSignoffCreate = Body(..., openapi_examples=SIGNOFF_OPENAPI_EXAMPLES),
    actor_role: str = Depends(get_actor_role),
    db: Session = Depends(get_db),
):
    # RBAC
    try:
        ensure_allowed("deliverable.signoff", actor_role)
    except Forbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

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
def list_signoffs(
    deliverable_id: UUID,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    ),
    db: Session = Depends(get_db),
):
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


@router.post("/{deliverable_id}/submit_to_qc",
    response_model=DeliverableRead,
    summary="Submit deliverable to QC",
    description=(
        "Отправляет изделие в QC: deliverable.status → `submitted_to_qc`.\n\n"
        "Gate (MVP): требуется последний production sign-off со значением `approved`.\n"
        "Разрешено только из статусов `open` и `qc_rejected`."
        ),
    )
def submit_to_qc(
    deliverable_id: UUID,
    body: SubmitToQcRequest = Body(..., openapi_examples=SUBMIT_TO_QC_OPENAPI_EXAMPLES),
    actor_role: str = Depends(get_actor_role),
    db: Session = Depends(get_db),
):
    # RBAC
    try:
        ensure_allowed("deliverable.submit_to_qc", actor_role)
    except Forbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

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

    _ = body.actor_user_id  # TODO: писать audit event submit_to_qc

    d.status = DeliverableStatus.submitted_to_qc.value
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.get("/{deliverable_id}/qc_inspections", response_model=list[QcInspectionRead])
def list_qc_inspections(
    deliverable_id: UUID,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    ),
    db: Session = Depends(get_db),
):
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


@router.post(
    "/{deliverable_id}/qc_decision",
    response_model=DeliverableRead,
    summary="QC decision for deliverable (approve / reject)",
    description=(
        "Решение отдела контроля качества по изделию.\n\n"
        "- `approved`: изделие проходит QC, статус deliverable → `qc_approved`\n"
        "- `rejected`: изделие отклонено, статус → `qc_rejected`, "
        "и автоматически создаётся fix-task, привязанный к deliverable.\n\n"
        "Для `rejected` поле `notes` обязательно и используется как причина отклонения."
    ),
)
def qc_decision(
    deliverable_id: UUID,
    body: QcDecisionRequest = Body(..., openapi_examples=QC_DECISION_OPENAPI_EXAMPLES),
    actor_role: str = Depends(get_actor_role),
    db: Session = Depends(get_db),
):
    # RBAC
    try:
        ensure_allowed("deliverable.qc_decision", actor_role)
    except Forbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

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
        # (создание fix-task у тебя тут уже есть — оставляем как есть или позже переведём на TaskFixService)
        # гарантируем qc.id (если id генерится python-ом — flush не обязателен, но безопасен)
        db.flush()

        svc = TaskFixService(db)

        fix_title = f"Исправление (QC): {d.deliverable_type} {d.serial}"
        fix_title = fix_title[:250]  # чтобы не разрастался

        svc.create_qc_reject_fix(
            deliverable=d,
            actor_user_id=body.inspector_user_id,
            qc_inspection_id=qc.id,
            title=fix_title,
            description=body.notes,
            severity=FixSeverity.major,
        )


    db.add(d)
    db.commit()
    db.refresh(d)
    return d

@router.get("/{deliverable_id}/tasks", response_model=list[TaskRead])
def list_deliverable_tasks(
    deliverable_id: UUID,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    ),
    db: Session = Depends(get_db),
):
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
def get_dashboard(
    deliverable_id: UUID,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    ),
    db: Session = Depends(get_db),
):
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

@router.post(
    "/{deliverable_id}/bootstrap",
    response_model=DeliverableBootstrapResponse,
    summary="Bootstrap tasks for deliverable",
    description=(
        "Создаёт задачи и зависимости по активной версии шаблона проекта и привязывает их к deliverable.\n\n"
        "Операция тяжёлая и не должна вызываться повторно для одного deliverable без явного reset/rollback.\n"
        "Доступ ограничен RBAC."
    ),
)
def bootstrap_deliverable(
    deliverable_id: UUID,
    body: DeliverableBootstrapRequest = Body(..., openapi_examples=DELIVERABLE_BOOTSTRAP_OPENAPI_EXAMPLES),
    actor_role: str = Depends(get_actor_role),
    db: Session = Depends(get_db),
):
    # RBAC
    try:
        ensure_allowed("deliverable.bootstrap", actor_role)
    except Forbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    service = DeliverableBootstrapService(db)

    try:
        with db.begin():
            result = service.bootstrap(
                org_id=body.org_id,
                project_id=body.project_id,
                deliverable_id=deliverable_id,
                actor_user_id=body.actor_user_id,
            )
    except BootstrapError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return DeliverableBootstrapResponse(
        template_version_id=result.template_version_id,
        created_tasks=result.created_tasks,
        created_dependencies=result.created_dependencies,
    )


@router.post("/{deliverable_id}/fix-tasks", response_model=TaskRead)
def create_deliverable_fix(
    deliverable_id: UUID,
    cmd: Command[DeliverableFixPayload] = Body(..., openapi_examples=DELIVERABLE_FIX_OPENAPI_EXAMPLES),
    db: Session = Depends(get_db),
):
    deliverable = db.get(Deliverable, deliverable_id)
    if not deliverable:
        raise HTTPException(404, "Deliverable not found")

    svc = TaskFixService(db)

    fix = svc.create_initiative_fix_for_deliverable(
        deliverable=deliverable,
        actor_user_id=cmd.actor_user_id,
        title=cmd.payload.title,
        description=cmd.payload.description,
        severity=cmd.payload.severity,
        minutes_spent=cmd.payload.minutes_spent,
        attachments=[a.model_dump() for a in cmd.payload.attachments] if cmd.payload.attachments else None,
    )

    db.commit()
    db.refresh(fix)
    return fix
