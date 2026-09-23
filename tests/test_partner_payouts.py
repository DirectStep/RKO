from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain.enums import BankInternalStatus, PaymentStatus
from app.domain.operations import DomainError
from app.domain.partner_economics import partner_reward
from app.services.sheets_snapshot import partner_payout_row


def test_partner_gets_twenty_percent_after_lead_payment() -> None:
    assert partner_reward(Decimal("10000"), Decimal("3000")) == Decimal("1400.00")
    assert partner_reward(Decimal("10000"), Decimal("2800")) == Decimal("1440.00")


def test_lead_payment_cannot_exceed_bank_income() -> None:
    with pytest.raises(DomainError, match="превышать"):
        partner_reward(Decimal("1000"), Decimal("1100"))


def test_partner_sheet_row_tracks_one_selected_bank_and_payment() -> None:
    partner = SimpleNamespace(telegram_username="partner", name="Partner")
    lead = SimpleNamespace(
        telegram_username="client",
        telegram_id="123",
        application_at=datetime(2026, 9, 22, 20, tzinfo=UTC),
    )
    bank = SimpleNamespace(name="Альфа-Банк")
    lead_bank = SimpleNamespace(
        internal_status=BankInternalStatus.PLANNED, partner_reward_fact=None
    )
    row = partner_payout_row(partner, lead, lead_bank, bank, None)
    assert row == ["@partner", "@client", "Альфа-Банк", "22.09.2026", "Не активирован", "", "", ""]
    lead_bank.partner_reward_fact = Decimal("600.00")
    assert partner_payout_row(partner, lead, lead_bank, bank, None)[5:] == ["", "", ""]

    lead_bank.internal_status = BankInternalStatus.ACCOUNT_OPENED
    lead_bank.partner_reward_fact = Decimal("1440.00")
    payment = SimpleNamespace(
        status=PaymentStatus.AWAITING_CONFIRMATION,
        partner_reward_fact=Decimal("1440.00"),
        paid_at=None,
    )
    row = partner_payout_row(partner, lead, lead_bank, bank, payment)
    assert row[4:] == ["Активирован", 1440.0, "Не выплачено", ""]

    payment.status = PaymentStatus.PAID
    payment.paid_at = date(2026, 9, 25)
    row = partner_payout_row(partner, lead, lead_bank, bank, payment)
    assert row[4:] == ["Активирован", 1440.0, "Выплачено", "25.09.2026"]
