# app/schemas/transition.py
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, conint


# ============================================================================
# PAYLOAD MODELS (строго под action из task_fsm.py)
# ============================================================================

class EmptyPayload(BaseModel):
    """
    Payload для действий, где тело не требуется:
    plan, unassign, start, submit, approve, cancel
    """
    pass


class AssignPayload(BaseModel):
    """
    Payload для action=assign: назначить исполнителя.
    """
    assign_to: UUID = Field(
        ...,
        description="User ID исполнителя",
        examples=["33333333-3333-3333-3333-333333333333"],
    )


class RejectPayload(BaseModel):
    """
    Payload для action=reject: отклонить задачу и (опционально) создать fix-task.

    ВАЖНО: reject всегда переводит в status=rejected (зафиксировано в FSM).
    Возврат в работу происходит через создание fix-task (side-effect FSM).
    """
    reason: str = Field(
        ...,
        min_length=1,
        description="Причина отклонения",
        examples=["Найдены дефекты, требуется доработка"],
    )
    fix_title: Optional[str] = Field(
        None,
        description="Заголовок для fix-task (опционально)",
        examples=["Исправить дефекты по задаче"],
    )
    assign_to: Optional[UUID] = Field(
        None,
        description="User ID для fix-task (опционально)",
        examples=["33333333-3333-3333-3333-333333333333"],
    )


# ============================================================================
# COMMON REQUEST FIELDS
# ============================================================================

class TransitionCommon(BaseModel):
    """
    Общие поля для всех transition requests.
    """
    org_id: UUID = Field(
        ...,
        description="Организация (мультитенантность). Пока передаём явно, позже будет из auth.",
        examples=["11111111-1111-1111-1111-111111111111"],
    )
    actor_user_id: UUID = Field(
        ...,
        description="Кто выполняет действие. Пока передаём явно, позже будет из auth.",
        examples=["33333333-3333-3333-3333-333333333333"],
    )
    expected_row_version: conint(ge=1) = Field(
        ...,
        description="Optimistic lock: ожидаемая версия строки задачи (начинается с 1)",
        examples=[1],
    )
    client_event_id: Optional[UUID] = Field(
        None,
        description="Idempotency key (UUID). Опционально. Повтор с тем же значением не даёт побочный эффект.",
        examples=["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
    )


# ============================================================================
# ACTION-SPECIFIC REQUEST MODELS (discriminator = action)
# ============================================================================
# Все actions из task_fsm.py:
# PLAN, ASSIGN, UNASSIGN, START, SUBMIT, APPROVE, REJECT, CANCEL

class PlanRequest(TransitionCommon):
    """
    Action: plan
    Переход: new -> planned
    Payload: пустой
    """
    action: Literal["plan"] = "plan"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class AssignRequest(TransitionCommon):
    """
    Action: assign
    Переход: new/planned -> assigned
    Payload: {assign_to: UUID}
    """
    action: Literal["assign"] = "assign"
    payload: AssignPayload


class UnassignRequest(TransitionCommon):
    """
    Action: unassign
    Переход: assigned -> planned
    Payload: пустой
    """
    action: Literal["unassign"] = "unassign"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class StartRequest(TransitionCommon):
    """
    Action: start
    Переход: assigned -> in_progress
    Payload: пустой
    """
    action: Literal["start"] = "start"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class SubmitRequest(TransitionCommon):
    """
    Action: submit
    Переход: in_progress -> in_review
    Payload: пустой
    """
    action: Literal["submit"] = "submit"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class ApproveRequest(TransitionCommon):
    """
    Action: approve
    Переход: in_review -> done
    Payload: пустой
    """
    action: Literal["approve"] = "approve"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class RejectRequest(TransitionCommon):
    """
    Action: reject
    Переход: in_review -> rejected
    Payload: {reason, fix_title?, assign_to?}
    Side-effect: создаёт fix-task
    """
    action: Literal["reject"] = "reject"
    payload: RejectPayload


class CancelRequest(TransitionCommon):
    """
    Action: cancel
    Переход: любой нефинальный -> canceled
    Payload: пустой
    """
    action: Literal["cancel"] = "cancel"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


# ============================================================================
# DISCRIMINATED UNION
# ============================================================================

TaskTransitionRequest = Annotated[
    Union[
        PlanRequest,
        AssignRequest,
        UnassignRequest,
        StartRequest,
        SubmitRequest,
        ApproveRequest,
        RejectRequest,
        CancelRequest,
    ],
    Field(discriminator="action"),
]


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class TaskTransitionResponse(BaseModel):
    task_id: UUID
    status: str
    row_version: int
    fix_task_id: Optional[UUID] = None


# ============================================================================
# LEGACY COMPATIBILITY (если нужно для других частей API)
# ============================================================================
# Если где-то используется старый TaskTransitionItem, оставляем для совместимости

from datetime import datetime
from typing import Any


class TaskTransitionItem(BaseModel):
    """
    Модель для чтения истории transitions (GET /tasks/{id}/transitions).
    """
    id: UUID
    task_id: UUID
    action: str  # не enum, т.к. из БД приходит строка
    from_status: str
    to_status: str
    payload: dict[str, Any]  # исторический payload, не типизированный
    actor_user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}