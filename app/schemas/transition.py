# app/schemas/transition.py
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, conint


class StrictBaseModel(BaseModel):
    """Strict request models: forbid unknown fields.

    API Hardening (A1): remove "gray zones" by rejecting any extra keys in
    request bodies and nested payloads.
    """

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# PAYLOAD MODELS (strictly per actions in app/fsm/task_fsm.py)
# ============================================================================


class EmptyPayload(StrictBaseModel):
    """Payload for actions where body is not required."""


class AssignPayload(StrictBaseModel):
    """Payload for action=assign (leader assigns executor)."""

    assign_to: UUID = Field(
        ...,
        description="User ID исполнителя",
        examples=["33333333-3333-3333-3333-333333333333"],
    )


class ReviewRejectPayload(StrictBaseModel):
    """Payload for action=review_reject.

    Возвращает задачу в работу (submitted -> in_progress). Опционально может породить fix-task
    (через side-effect сервиса).
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


class EscalatePayload(StrictBaseModel):
    """Payload for action=escalate (no status change)."""

    message: str = Field(
        ...,
        min_length=1,
        description="Сообщение/сигнал лиду: нужна помощь/переназначение",
        examples=["Нужна помощь: нет инструмента/не уверен в операции"],
    )


# ============================================================================
# COMMON REQUEST FIELDS
# ============================================================================


class TransitionCommon(StrictBaseModel):
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
        description="Idempotency key (UUID). Опционально.",
        examples=["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
    )


# ============================================================================
# ACTION-SPECIFIC REQUEST MODELS (discriminator = action)
# ============================================================================


class UnblockRequest(TransitionCommon):
    """Action: unblock (blocked -> available)."""

    action: Literal["unblock"] = "unblock"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class SelfAssignRequest(TransitionCommon):
    """Action: self_assign (available -> assigned)."""

    action: Literal["self_assign"] = "self_assign"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class AssignRequest(TransitionCommon):
    """Action: assign (available -> assigned)."""

    action: Literal["assign"] = "assign"
    payload: AssignPayload


class StartRequest(TransitionCommon):
    """Action: start (assigned -> in_progress)."""

    action: Literal["start"] = "start"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class SubmitRequest(TransitionCommon):
    """Action: submit (in_progress -> submitted)."""

    action: Literal["submit"] = "submit"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class ReviewApproveRequest(TransitionCommon):
    """Action: review_approve (submitted -> done)."""

    action: Literal["review_approve"] = "review_approve"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class ReviewRejectRequest(TransitionCommon):
    """Action: review_reject (submitted -> in_progress)."""

    action: Literal["review_reject"] = "review_reject"
    payload: ReviewRejectPayload


class ShiftReleaseRequest(TransitionCommon):
    """Action: shift_release (assigned/in_progress -> available)."""

    action: Literal["shift_release"] = "shift_release"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class RecallToPoolRequest(TransitionCommon):
    """Action: recall_to_pool (assigned/in_progress -> available)."""

    action: Literal["recall_to_pool"] = "recall_to_pool"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class EscalateRequest(TransitionCommon):
    """Action: escalate (no status change)."""

    action: Literal["escalate"] = "escalate"
    payload: EscalatePayload


class CancelRequest(TransitionCommon):
    """Action: cancel (any non-terminal -> canceled)."""

    action: Literal["cancel"] = "cancel"
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


TaskTransitionRequest = Annotated[
    Union[
        UnblockRequest,
        SelfAssignRequest,
        AssignRequest,
        StartRequest,
        SubmitRequest,
        ReviewApproveRequest,
        ReviewRejectRequest,
        ShiftReleaseRequest,
        RecallToPoolRequest,
        EscalateRequest,
        CancelRequest,
    ],
    Field(discriminator="action"),
]


class TaskTransitionResponse(BaseModel):
    task_id: UUID
    status: str
    row_version: int
    fix_task_id: Optional[UUID] = None


class TaskTransitionItem(BaseModel):
    """Модель для чтения истории transitions (GET /tasks/{id}/transitions)."""

    id: UUID
    task_id: UUID
    action: str
    from_status: str
    to_status: str
    created_at: Optional[str] = None
    payload: Optional[dict] = None
