from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.domain.enums import BankInternalStatus, PaymentStatus
from app.domain.partner_economics import partner_reward
from app.services.lead_assignment import LeadAssignmentService
from app.services.sheets_snapshot import partner_payout_row
from app.services.workflow import WorkflowService


def test_partner_gets_twenty_percent_after_lead_payment() -> None:
    assert partner_reward(Decimal("10000"), Decimal("3000"), Decimal("20")) == Decimal("1400.00")
    assert partner_reward(Decimal("10000"), Decimal("2800"), Decimal("20")) == Decimal("1440.00")


def test_partner_reward_uses_saved_fractional_percent() -> None:
    assert partner_reward(Decimal("10000"), Decimal("3000"), Decimal("17.50")) == Decimal("1225.00")
    assert partner_reward(Decimal("10000"), Decimal("3000"), Decimal("0")) == Decimal("0.00")
    assert partner_reward(Decimal("10000"), Decimal("3000"), Decimal("100")) == Decimal("7000.00")
    assert WorkflowService._reward(
        Decimal("10000"), Decimal("3000"), Decimal("17.50")
    ) == Decimal("1225.00")


def test_return_to_original_partner_keeps_application_percent() -> None:
    original_id, other_id = uuid4(), uuid4()
    lead = SimpleNamespace(
        partner_id=other_id,
        partner_percent_snapshot=Decimal("7.50"),
        original_partner_id=original_id,
        original_partner_percent_snapshot=Decimal("20.00"),
    )
    original = SimpleNamespace(id=original_id, commission_percent=Decimal("30.00"))
    assert LeadAssignmentService._percent_for_partner(lead, original) == Decimal("20.00")


def test_partner_gets_zero_and_team_keeps_the_loss() -> None:
    assert partner_reward(Decimal("1000"), Decimal("1100"), Decimal("20")) == Decimal("0.00")
    assert partner_reward(Decimal("1000"), None, Decimal("20")) is None


def test_partner_sheet_row_tracks_one_selected_bank_and_payment() -> None:
    partner = SimpleNamespace(telegram_username="partner", name="Partner")
    lead = SimpleNamespace(
        telegram_username="client",
        telegram_id="123",
        application_at=datetime(2026, 9, 22, 20, tzinfo=UTC),
    )
    bank = SimpleNamespace(name="Альфа-Банк")
    lead_bank = SimpleNamespace(
        internal_status=BankInternalStatus.PLANNED,
        partner_reward_fact=None,
        lead_reward_paid_at=None,
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
    assert row[4:] == ["Активирован", "", "", ""]
    lead_bank.lead_reward_paid_at = datetime(2026, 9, 24, tzinfo=UTC)
    row = partner_payout_row(partner, lead, lead_bank, bank, payment)
    assert row[4:] == ["Активирован", 1440.0, "Не выплачено", ""]

    payment.status = PaymentStatus.PAID
    payment.paid_at = date(2026, 9, 25)
    row = partner_payout_row(partner, lead, lead_bank, bank, payment)
    assert row[4:] == ["Активирован", 1440.0, "Выплачено", "25.09.2026"]
