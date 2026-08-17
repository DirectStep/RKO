from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from app.domain.enums import AssignmentStatus, PaymentStatus, UserRole


class DomainError(ValueError):
    pass


@dataclass(frozen=True)
class AssignmentConfirmation:
    partner_id: UUID
    channel_id: UUID
    confirmed_at: datetime


@dataclass(frozen=True)
class PaymentConfirmation:
    amount: Decimal
    confirmed_at: datetime
    confirmed_by_user_id: UUID


PAYMENT_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.NOT_CALCULATED: frozenset({PaymentStatus.CALCULATED}),
    PaymentStatus.CALCULATED: frozenset(
        {PaymentStatus.AWAITING_CONFIRMATION, PaymentStatus.CANCELLED}
    ),
    PaymentStatus.AWAITING_CONFIRMATION: frozenset(
        {PaymentStatus.CONFIRMED, PaymentStatus.CANCELLED}
    ),
    PaymentStatus.CONFIRMED: frozenset(
        {PaymentStatus.IN_REGISTRY, PaymentStatus.PAID, PaymentStatus.CANCELLED}
    ),
    PaymentStatus.IN_REGISTRY: frozenset({PaymentStatus.PAID, PaymentStatus.CANCELLED}),
    PaymentStatus.PAID: frozenset(),
    PaymentStatus.CANCELLED: frozenset(),
}


def confirm_assignment(
    *,
    actor_role: UserRole,
    current_status: AssignmentStatus,
    partner_id: UUID | None,
    channel_id: UUID | None,
    confirmed_at: datetime,
) -> AssignmentConfirmation:
    if actor_role is not UserRole.ADMIN:
        raise DomainError("Источник может подтвердить только администратор")
    if current_status is not AssignmentStatus.PENDING:
        raise DomainError("Источник можно подтвердить только из статуса ожидания")
    if partner_id is None or channel_id is None:
        raise DomainError("Для подтверждения нужны партнёр и канал")
    return AssignmentConfirmation(partner_id, channel_id, confirmed_at)


def confirm_payment(
    *,
    actor_role: UserRole,
    current_status: PaymentStatus,
    amount: Decimal,
    confirmed_at: datetime,
    confirmed_by_user_id: UUID,
) -> PaymentConfirmation:
    if actor_role is not UserRole.ADMIN:
        raise DomainError("Выплату может подтвердить только администратор")
    if current_status is not PaymentStatus.AWAITING_CONFIRMATION:
        raise DomainError("Подтвердить можно только выплату, ожидающую подтверждения")
    if amount < 0:
        raise DomainError("Сумма выплаты не может быть отрицательной")
    return PaymentConfirmation(amount, confirmed_at, confirmed_by_user_id)


def validate_payment_transition(
    *,
    actor_role: UserRole,
    current_status: PaymentStatus,
    new_status: PaymentStatus,
    paid_at: date | None = None,
    internal_comment: str | None = None,
) -> None:
    if actor_role is not UserRole.ADMIN:
        raise DomainError("Статус выплаты может менять только администратор")
    if new_status is current_status:
        return
    if new_status not in PAYMENT_TRANSITIONS[current_status]:
        raise DomainError("Недопустимый переход статуса выплаты")
    if new_status is PaymentStatus.PAID:
        if current_status not in {PaymentStatus.CONFIRMED, PaymentStatus.IN_REGISTRY}:
            raise DomainError("Выплатить можно только подтверждённую сумму")
        if paid_at is None:
            raise DomainError("Для выплаченной суммы нужна дата")
    if new_status is PaymentStatus.CANCELLED and not (internal_comment or "").strip():
        raise DomainError("Для отмены нужен внутренний комментарий")
