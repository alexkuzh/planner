# app/api/tasks.py

from fastapi import APIRouter, Depends, HTTPException, status, Body, Query

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from uuid import UUID

from app.services.task_fix_service import TaskFixService
from app.services.task_transition_service import apply_task_transition, VersionConflict, IdempotencyConflict

from app.core.db import get_db
from app.core.rbac import ensure_allowed, Forbidden

from app.fsm.task_fsm import TransitionNotAllowed

from app.schemas.task import TaskCreate, TaskRead, TaskUpdate, TaskBlockerRead, TaskDependencyCreate, TaskDependencyRead
from app.schemas.task_event import TaskEventRead
from app.schemas.transition import TaskTransitionRequest, TaskTransitionResponse, TaskTransitionItem
from app.schemas.command import Command
from app.schemas.fix_task import ReportFixPayload
from app.schemas.error import ErrorResponse

from app.models.task import Task, TaskStatus, WorkKind
from app.models.task_event import TaskEvent
from app.models.task_transition import TaskTransition
from app.models.deliverable import Deliverable

from app.api.deps import get_actor_role

TASK_TRANSITION_OPENAPI_EXAMPLES = {
    "unblock": {
        "summary": "Unblock task",
        "description": "Перевести задачу из blocked в available (готова к выдаче/выбору).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "unblock",
            "expected_row_version": 1,
            "client_event_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "payload": {},
        },
    },
    "self_assign": {
        "summary": "Self-assign (pick from pool)",
        "description": "Исполнитель выбирает задачу из пула (available -> assigned).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "self_assign",
            "expected_row_version": 2,
            "client_event_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "payload": {},
        },
    },
    "assign": {
        "summary": "Assign task (leader)",
        "description": "Лид назначает исполнителя (available -> assigned).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "assign",
            "expected_row_version": 3,
            "client_event_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "payload": {"assign_to": "33333333-3333-3333-3333-333333333333"},
        },
    },
    "start": {
        "summary": "Start task",
        "description": "Начать работу (assigned -> in_progress).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "start",
            "expected_row_version": 4,
            "client_event_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "payload": {},
        },
    },
    "submit": {
        "summary": "Submit task",
        "description": "Отправить результат на проверку (in_progress -> submitted).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "submit",
            "expected_row_version": 5,
            "client_event_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            "payload": {},
        },
    },
    "review_approve": {
        "summary": "Approve submitted task",
        "description": "Принять результат (submitted -> done).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "review_approve",
            "expected_row_version": 6,
            "client_event_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "payload": {},
        },
    },
    "review_reject": {
        "summary": "Reject submitted task",
        "description": "Отклонить результат и вернуть в работу (submitted -> in_progress).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "review_reject",
            "expected_row_version": 7,
            "client_event_id": "11111111-2222-3333-4444-555555555555",
            "payload": {
                "reason": "Найдены дефекты, требуется доработка",
                "fix_title": "Исправить дефекты по задаче",
                "assign_to": "33333333-3333-3333-3333-333333333333"
            },
        },
    },
    "shift_release": {
        "summary": "Shift release",
        "description": "Автоматически вернуть задачу в пул в конце смены (assigned/in_progress -> available).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "shift_release",
            "expected_row_version": 8,
            "client_event_id": "22222222-2222-3333-4444-555555555555",
            "payload": {},
        },
    },
    "recall_to_pool": {
        "summary": "Recall to pool (leader)",
        "description": "Лид принудительно отзывает задачу в пул (assigned/in_progress -> available).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "recall_to_pool",
            "expected_row_version": 9,
            "client_event_id": "33333333-2222-3333-4444-555555555555",
            "payload": {},
        },
    },
    "escalate": {
        "summary": "Escalate",
        "description": "Сигнал лидu: нужна помощь/переназначение (без смены статуса).",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "action": "escalate",
            "expected_row_version": 10,
            "client_event_id": "44444444-2222-3333-4444-555555555555",
            "payload": {"message": "Нужна помощь: нет инструмента/не уверен в операции"},
        },
    },
}

REPORT_FIX_OPENAPI_EXAMPLES = {
    "worker_initiative_fix": {
        "summary": "Report fix (worker initiative)",
        "description": "Работник заметил косяк и исправил — фиксируем время и серьёзность.",
        "value": {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "actor_user_id": "33333333-3333-3333-3333-333333333333",
            "expected_row_version": 1,
            "client_event_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "payload": {
                "title": "Исправил косяк по месту",
                "description": "Нашёл дефект на соседнем этапе и устранил.",
                "severity": "minor",
                "minutes_spent": 15,
                "attachments": []
            }
        },
    }
}

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_task_in_org_or_404(db: Session, *, org_id: UUID, task_id: UUID) -> Task:
    task = db.execute(
        select(Task).where(Task.org_id == org_id, Task.id == task_id)
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, db: Session = Depends(get_db)):
    if data.deliverable_id is not None:
        d = db.get(Deliverable, data.deliverable_id)
        if not d:
            raise HTTPException(status_code=404, detail="Deliverable not found")
        if d.org_id != data.org_id:
            raise HTTPException(status_code=422, detail="Deliverable org_id mismatch")

    task = Task(
        org_id=data.org_id,
        project_id=data.project_id,
        created_by=data.created_by,
        title=data.title,
        description=data.description,
        priority=data.priority,
        # По финальной модели задачи создаются в blocked и становятся available
        # только после разрешения зависимостей/холдов.
        status=TaskStatus.blocked.value,

        kind=data.kind.value if hasattr(data.kind, "value") else str(data.kind),
        work_kind=WorkKind.work,  # ⬅️ СТРАХОВКА
        other_kind_label=data.other_kind_label,

        deliverable_id=data.deliverable_id,
        is_milestone=data.is_milestone,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post(
    "/{task_id}/transitions",
    response_model=TaskTransitionResponse,
    response_model_exclude_none=True,
    summary="Apply FSM transition to task",
    description=(
        "Применяет действие FSM к задаче (например: unblock/self_assign/assign/start/submit/review_approve/review_reject/shift_release/recall_to_pool/escalate).\n\n"
        "Требует optimistic lock: expected_row_version должен совпадать с текущим row_version задачи.\n"
        "payload зависит от action (см. примеры в Swagger)."
    ),
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized (missing or invalid auth headers)"},
        403: {"model": ErrorResponse, "description": "Forbidden (RBAC: action not allowed for this role)"},
        404: {"model": ErrorResponse, "description": "Task not found"},
        409: {"model": ErrorResponse, "description": "Conflict (row_version mismatch or idempotency conflict)"},
        422: {"model": ErrorResponse, "description": "FSM validation error / blocked / invalid transition"},
    },
)
def transition_task(
    task_id: UUID,
    payload: TaskTransitionRequest = Body(..., openapi_examples=TASK_TRANSITION_OPENAPI_EXAMPLES),
    actor_role: str = Depends(get_actor_role),
    db: Session = Depends(get_db),
):
    # --- Guard: QC actions are not allowed in Task FSM (Variant A) ---
    # TODO(qc): move QC actions to separate router / FSM
    if payload.action.startswith("qc_"):
        raise HTTPException(
            status_code=422,
            detail=(
                "QC actions are not allowed for Task transitions. "
                "Use qc_inspections / deliverable QC flow instead."
            ),
        )
    # RBAC: разрешение зависит от action
    try:
        ensure_allowed(f"task.{payload.action}", actor_role)
    except Forbidden as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        with db.begin():
            try:
                task, fix_task = apply_task_transition(
                    db,
                    org_id=payload.org_id,
                    actor_user_id=payload.actor_user_id,
                    task_id=task_id,
                    action=payload.action,
                    expected_row_version=payload.expected_row_version,
                    payload=payload.payload,
                    client_event_id=payload.client_event_id,
                )
            except IdempotencyConflict as e:
                raise HTTPException(status_code=409, detail=str(e))

        return TaskTransitionResponse(
            task_id=task.id,
            status=task.status,          # строка
            row_version=task.row_version,
            fix_task_id=fix_task.id if fix_task else None,
        )

    except VersionConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except TransitionNotAllowed as e:
        raise HTTPException(status_code=422, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")


@router.post("/{task_id}/dependencies", status_code=201)
def add_dependency(
        org_id: UUID = Query(
        ...,
            description="Организация (мультитенантность). Пока query, позже будет из auth.",
            examples=["11111111-1111-1111-1111-111111111111"],
        ),
        created_by: UUID = Query(
        ...,
            description="Кто создал зависимость (audit). Пока query, позже будет из auth.",
            examples=["33333333-3333-3333-3333-333333333333"],
        ),
        body: TaskDependencyCreate = Body(...),
        db: Session = Depends(get_db)):
    """
    Создаёт зависимость predecessor -> successor(task_id).
    org_id и created_by пока query-параметры (позже заберём из auth).
    """
    # Проверяем обе задачи в этой org
    succ = db.execute(select(Task).where(Task.org_id == org_id, Task.id == task_id)).scalar_one_or_none()
    pred = db.execute(select(Task).where(Task.org_id == org_id, Task.id == body.predecessor_id)).scalar_one_or_none()
    if not succ or not pred:
        raise HTTPException(status_code=404, detail="Task not found in org")

    if body.predecessor_id == task_id:
        raise HTTPException(status_code=422, detail="Dependency cannot be self-referential")

    try:
        db.execute(
            text("""
                INSERT INTO task_dependencies (org_id, project_id, predecessor_id, successor_id, created_by, created_at)
                VALUES (:org_id, :project_id, :pred, :succ, :created_by, now())
            """),
            {
                "org_id": str(org_id),
                "project_id": str(succ.project_id),
                "pred": str(body.predecessor_id),
                "succ": str(task_id),
                "created_by": str(created_by),
            },
        )
        db.commit()
    except Exception as e:
        # primary key (org_id, predecessor_id, successor_id) защитит от дублей
        raise HTTPException(status_code=409, detail=f"Dependency already exists or insert failed: {e}")

    return {"ok": True}


from fastapi import Query

@router.get("", response_model=list[TaskRead])
def list_tasks(
    org_id: UUID = Query(..., description="Организация"),
    project_id: UUID = Query(..., description="Проект"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return (
        db.query(Task)
        .filter(Task.org_id == org_id, Task.project_id == project_id)
        .order_by(Task.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )



@router.get("/{task_id}/transitions", response_model=list[TaskTransitionItem], response_model_exclude_none=True, )
def list_task_transitions(
    task_id: UUID,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    ),
    db: Session = Depends(get_db),
):
    """
    Timeline переходов FSM по задаче.
    org_id пока передаём query-параметром (мультитенантность), позже заменим на auth-context.
    """
    # Проверим что задача существует в этой org (мультитенантность)
    task = db.execute(select(Task).where(Task.org_id == org_id, Task.id == task_id)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    transitions = (
        db.query(TaskTransition)
        .filter(TaskTransition.org_id == org_id, TaskTransition.task_id == task_id)
        .order_by(TaskTransition.created_at.asc())
        .all()
    )
    return transitions

@router.get("/{task_id}/dependencies", response_model=list[TaskDependencyRead])
def list_dependencies(
    task_id: UUID,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    ),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT predecessor_id, successor_id, created_by, created_at
            FROM task_dependencies
            WHERE org_id = :org_id
              AND successor_id = :task_id
            ORDER BY created_at ASC
        """),
        {"org_id": str(org_id), "task_id": str(task_id)},
    ).mappings().all()
    return list(rows)


@router.get("/{task_id}/blockers", response_model=list[TaskBlockerRead])
def list_task_blockers(
    task_id: UUID,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    ),
    db: Session = Depends(get_db),
):
    # проверка существования задачи в org
    task = db.execute(
        select(Task).where(Task.org_id == org_id, Task.id == task_id)
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # blockers = predecessor задачи, которые еще не done
    rows = db.execute(
        text("""
            SELECT t.id, t.title, t.status, t.priority
            FROM task_dependencies d
            JOIN tasks t
              ON t.id = d.predecessor_id
             AND t.org_id = d.org_id
            WHERE d.org_id = :org_id
              AND d.successor_id = :task_id
              AND t.status <> 'done'
            ORDER BY t.priority DESC, t.created_at ASC
        """),
        {"org_id": str(org_id), "task_id": str(task_id)},
    ).mappings().all()

    # mappings() -> dict-like, Pydantic спокойно съест
    return list(rows)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: UUID,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
        ),
    db: Session = Depends(get_db),
    ):
    task = db.execute(select(Task).where(Task.org_id == org_id, Task.id == task_id)).scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/events", response_model=list[TaskEventRead])
def list_task_events(task_id: UUID, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return (
        db.query(TaskEvent)
        .filter(TaskEvent.task_id == task_id)
        .order_by(TaskEvent.id.asc())
        .all()
    )


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    ),
    db: Session = Depends(get_db),
):
    task = get_task_in_org_or_404(db, org_id=org_id, task_id=task_id)

    if payload.title is not None:
        task.title = payload.title

    if payload.deliverable_id is not None:
        task.deliverable_id = payload.deliverable_id

    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: UUID,
    org_id: UUID = Query(
        ...,
        description="Организация (мультитенантность). Пока query, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    ),
    db: Session = Depends(get_db),
):
    task = get_task_in_org_or_404(db, org_id=org_id, task_id=task_id)

    db.delete(task)
    db.commit()
    return None


@router.delete("/{task_id}/dependencies/{predecessor_id}", status_code=204)
def delete_dependency(task_id: UUID, predecessor_id: UUID, org_id: UUID, db: Session = Depends(get_db)):
    res = db.execute(
        text("""
            DELETE FROM task_dependencies
            WHERE org_id = :org_id
              AND successor_id = :task_id
              AND predecessor_id = :pred
        """),
        {"org_id": str(org_id), "task_id": str(task_id), "pred": str(predecessor_id)},
    )
    db.commit()
    return None

@router.post("/{task_id}/report-fix", response_model=TaskRead)
def report_fix(
    task_id: UUID,
    cmd: Command[ReportFixPayload] = Body(..., openapi_examples=REPORT_FIX_OPENAPI_EXAMPLES),
    db: Session = Depends(get_db),
):
    origin = db.get(Task, task_id)
    if not origin:
        raise HTTPException(404, "Task not found")
    if origin.deliverable_id is None:
        raise HTTPException(422, "Origin task must be linked to a deliverable for report-fix (use deliverable fix endpoint).")

    svc = TaskFixService(db)
    fix = svc.create_initiative_fix_for_task(
        origin_task=origin,
        actor_user_id=cmd.actor_user_id,
        title=cmd.payload.title,
        description=cmd.payload.description,
        severity=cmd.payload.severity,
        minutes_spent=cmd.payload.minutes_spent,
        attachments=[a.model_dump() for a in cmd.payload.attachments],
    )
    db.commit()
    db.refresh(fix)
    return fix
