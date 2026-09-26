from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.enums import PaymentStatus, UserRole
from app.domain.operations import DomainError
from app.services.workflow import WorkflowService
from app.workers.partner_payment_notifications import deliver_partner_payment_notification


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class PaymentSession:
    def __init__(self, lead_bank, payment):
        self.lead_bank = lead_bank
        self.payment = payment
        self.lead = SimpleNamespace(payment_status=PaymentStatus.NOT_CALCULATED)
        self.lookups = 0

    def begin(self):
        return AsyncContext(None)

    async def scalar(self, _query):
        self.lookups += 1
        return self.lead_bank if self.lookups % 2 else self.payment

    async def get(self, _model, _identity):
        return self.lead


class PaymentDatabase:
    def __init__(self, session):
        self.current = session

    def session(self):
        return AsyncContext(self.current)


@pytest.mark.asyncio
async def test_partner_payment_is_final_after_one_server_action_and_idempotent() -> None:
    lead_bank = SimpleNamespace(
        id=uuid4(),
        lead_id=uuid4(),
        partner_reward_fact=Decimal("1115.00"),
        lead_reward_paid_at=datetime.now(UTC),
        lead_reward_paid_separately=False,
    )
    payment = SimpleNamespace(
        status=PaymentStatus.AWAITING_CONFIRMATION,
        partner_reward_fact=Decimal("1115.00"),
        confirmed_at=None,
        confirmed_by_user_id=None,
        paid_at=None,
    )
    session = PaymentSession(lead_bank, payment)
    service = WorkflowService(PaymentDatabase(session))
    admin_id = uuid4()

    result, changed = await service.pay_lead_bank_partner(
        actor_role=UserRole.ADMIN, actor_user_id=admin_id, lead_bank_id=lead_bank.id
    )
    assert result is payment and changed
    assert payment.status is PaymentStatus.PAID
    assert payment.paid_at is not None
    assert payment.confirmed_by_user_id == admin_id
    assert session.lead.payment_status is PaymentStatus.PAID

    result, changed = await service.pay_lead_bank_partner(
        actor_role=UserRole.ADMIN, actor_user_id=admin_id, lead_bank_id=lead_bank.id
    )
    assert result is payment and not changed


@pytest.mark.asyncio
async def test_partner_payment_still_requires_lead_payment() -> None:
    lead_bank = SimpleNamespace(
        id=uuid4(), lead_id=uuid4(), partner_reward_fact=Decimal("50"),
        lead_reward_paid_at=None, lead_reward_paid_separately=False,
    )
    payment = SimpleNamespace(status=PaymentStatus.AWAITING_CONFIRMATION)
    service = WorkflowService(PaymentDatabase(PaymentSession(lead_bank, payment)))

    with pytest.raises(DomainError, match="выплату лиду"):
        await service.pay_lead_bank_partner(
            actor_role=UserRole.ADMIN, actor_user_id=uuid4(), lead_bank_id=lead_bank.id
        )


@pytest.mark.asyncio
async def test_failed_partner_notification_can_be_retried() -> None:
    payment = SimpleNamespace(
        status=PaymentStatus.PAID,
        partner_notification_sent_at=None,
        partner_reward_fact=Decimal("1115.00"),
    )
    details = SimpleNamespace(short_id="RKO-0052", name="Акбарс Банк", telegram_id="12345")

    class DeliverySession:
        def begin(self):
            return AsyncContext(None)

        async def scalar(self, _query):
            return payment

        async def execute(self, _query):
            return SimpleNamespace(one_or_none=lambda: details)

    database = PaymentDatabase(DeliverySession())
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("Telegram offline")))
    payment_id = uuid4()

    assert not await deliver_partner_payment_notification(database, (bot,), payment_id)
    assert payment.partner_notification_sent_at is None

    bot.send_message = AsyncMock()
    assert await deliver_partner_payment_notification(database, (bot,), payment_id)
    assert payment.partner_notification_sent_at is not None
    assert not await deliver_partner_payment_notification(database, (bot,), payment_id)
    assert bot.send_message.await_count == 1
