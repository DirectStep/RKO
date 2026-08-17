from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.enums import AssignmentStatus, PaymentStatus, UserRole
from app.domain.operations import (
    DomainError,
    confirm_assignment,
    confirm_payment,
    validate_payment_transition,
)


def test_manager_cannot_confirm_assignment() -> None:
    with pytest.raises(DomainError, match="администратор"):
        confirm_assignment(
            actor_role=UserRole.MANAGER,
            current_status=AssignmentStatus.PENDING,
            partner_id=uuid4(),
            channel_id=uuid4(),
            confirmed_at=datetime.now(UTC),
        )


def test_confirmed_assignment_is_immutable() -> None:
    with pytest.raises(DomainError, match="статуса ожидания"):
        confirm_assignment(
            actor_role=UserRole.ADMIN,
            current_status=AssignmentStatus.CONFIRMED,
            partner_id=uuid4(),
            channel_id=uuid4(),
            confirmed_at=datetime.now(UTC),
        )


def test_payment_confirmation_requires_admin_and_nonnegative_amount() -> None:
    with pytest.raises(DomainError, match="администратор"):
        confirm_payment(
            actor_role=UserRole.MANAGER,
            current_status=PaymentStatus.AWAITING_CONFIRMATION,
            amount=Decimal("100.00"),
            confirmed_at=datetime.now(UTC),
            confirmed_by_user_id=uuid4(),
        )
    with pytest.raises(DomainError, match="отрицательной"):
        confirm_payment(
            actor_role=UserRole.ADMIN,
            current_status=PaymentStatus.AWAITING_CONFIRMATION,
            amount=Decimal("-0.01"),
            confirmed_at=datetime.now(UTC),
            confirmed_by_user_id=uuid4(),
        )


def test_paid_requires_prior_confirmation_and_date() -> None:
    with pytest.raises(DomainError, match="Недопустимый переход"):
        validate_payment_transition(
            actor_role=UserRole.ADMIN,
            current_status=PaymentStatus.CALCULATED,
            new_status=PaymentStatus.PAID,
            paid_at=date.today(),
        )
    with pytest.raises(DomainError, match="нужна дата"):
        validate_payment_transition(
            actor_role=UserRole.ADMIN,
            current_status=PaymentStatus.CONFIRMED,
            new_status=PaymentStatus.PAID,
        )


def test_cancelled_payment_requires_comment() -> None:
    with pytest.raises(DomainError, match="комментарий"):
        validate_payment_transition(
            actor_role=UserRole.ADMIN,
            current_status=PaymentStatus.CALCULATED,
            new_status=PaymentStatus.CANCELLED,
            internal_comment="  ",
        )


@pytest.mark.parametrize(
    ("current_status", "new_status"),
    [
        (PaymentStatus.PAID, PaymentStatus.CALCULATED),
        (PaymentStatus.NOT_CALCULATED, PaymentStatus.IN_REGISTRY),
        (PaymentStatus.CANCELLED, PaymentStatus.AWAITING_CONFIRMATION),
    ],
)
def test_invalid_payment_status_jumps_are_rejected(
    current_status: PaymentStatus, new_status: PaymentStatus
) -> None:
    with pytest.raises(DomainError, match="Недопустимый переход"):
        validate_payment_transition(
            actor_role=UserRole.ADMIN,
            current_status=current_status,
            new_status=new_status,
        )


def test_payment_can_only_be_confirmed_from_awaiting_confirmation() -> None:
    with pytest.raises(DomainError, match="ожидающую подтверждения"):
        confirm_payment(
            actor_role=UserRole.ADMIN,
            current_status=PaymentStatus.NOT_CALCULATED,
            amount=Decimal("100.00"),
            confirmed_at=datetime.now(UTC),
            confirmed_by_user_id=uuid4(),
        )
