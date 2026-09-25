from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.domain.enums import BankInternalStatus
from app.services.application_progress import application_progress


NOW = datetime(2026, 9, 25, tzinfo=UTC)


def bank(
    status: BankInternalStatus,
    *,
    selected: bool = True,
    opened: bool = False,
    activated: bool = False,
    paid: bool = False,
    estimate: str = "1000",
    fact: str = "900",
) -> SimpleNamespace:
    return SimpleNamespace(
        internal_status=status,
        selected_by_lead=selected,
        account_opened_at=NOW if opened else None,
        opened_at=NOW if activated else None,
        lead_reward_paid_at=NOW if paid else None,
        lead_reward_estimate=Decimal(estimate),
        lead_reward_fact=Decimal(fact) if paid else None,
        lead_reward_paid_separately=False,
    )


def test_progress_counts_opened_and_activated_independently() -> None:
    banks = [
        bank(BankInternalStatus.ACCOUNT_OPENED, opened=True, activated=True),
        bank(BankInternalStatus.ACCOUNT_OPENED, opened=True, activated=True),
        bank(BankInternalStatus.AWAITING_ACTIVATION, opened=True),
        bank(BankInternalStatus.PLANNED),
        bank(BankInternalStatus.PLANNED),
    ]
    progress = application_progress(banks)
    assert progress["application_status"] == "opening_accounts"
    assert progress["bank_progress"] == {
        "opened": 3,
        "activated": 2,
        "total": 5,
        "expected_payout": "5000",
        "confirmed_payout": "0",
    }
    banks[3] = bank(BankInternalStatus.AWAITING_ACTIVATION, opened=True)
    banks[4] = bank(BankInternalStatus.AWAITING_ACTIVATION, opened=True)
    assert application_progress(banks)["application_status"] == "activating_accounts"


def test_terminal_decisions_complete_application_without_all_accounts_opened() -> None:
    banks = [
        bank(BankInternalStatus.ACCOUNT_OPENED, opened=True, activated=True, paid=True),
        bank(BankInternalStatus.CUT, opened=True, activated=True),
        bank(BankInternalStatus.NOT_OPENED),
        bank(BankInternalStatus.CLIENT_REFUSED, opened=True),
    ]
    progress = application_progress(banks)
    assert progress["application_status"] == "completed"
    assert progress["bank_progress"] == {
        "opened": 3,
        "activated": 2,
        "total": 4,
        "expected_payout": "0",
        "confirmed_payout": "900",
    }


def test_reoffered_bank_leaves_current_denominator_until_reselected() -> None:
    reoffered = bank(BankInternalStatus.NOT_OPENED, selected=False)
    selected = bank(BankInternalStatus.PLANNED)
    assert application_progress([selected, reoffered])["bank_progress"]["total"] == 1
    assert application_progress([reoffered])["application_status"] == "questionnaire_completed"
    reoffered.selected_by_lead = True
    reoffered.internal_status = BankInternalStatus.PLANNED
    assert application_progress([selected, reoffered])["bank_progress"]["total"] == 2
    assert application_progress([selected, reoffered])["application_status"] == "banks_selected"


def test_one_lead_can_have_expected_and_confirmed_bank_payouts_at_once() -> None:
    banks = [
        bank(BankInternalStatus.ACCOUNT_OPENED, opened=True, activated=True, paid=True),
        bank(BankInternalStatus.ACCOUNT_OPENED, opened=True, activated=True),
    ]
    progress = application_progress(banks)
    assert progress["application_status"] == "completed"
    assert progress["bank_progress"]["expected_payout"] == "1000"
    assert progress["bank_progress"]["confirmed_payout"] == "900"


def test_bank_paid_bonus_is_visible_to_lead_but_not_partner_or_admin() -> None:
    separate = bank(BankInternalStatus.ACCOUNT_OPENED, opened=True, activated=True)
    separate.lead_reward_paid_separately = True
    separate.lead_reward_estimate = Decimal("5000")
    assert application_progress([separate])["bank_progress"]["expected_payout"] == "0"
    lead_progress = application_progress([separate], include_bank_paid_lead_rewards=True)
    assert lead_progress["bank_progress"]["expected_payout"] == "5000"


def test_ineligible_questionnaire_has_its_own_status_without_banks() -> None:
    assert application_progress([])["application_status"] == "questionnaire_completed"
    result = application_progress([], not_eligible=True)
    assert result["application_status"] == "questionnaire_ineligible"
    assert result["bank_progress"]["total"] == 0
