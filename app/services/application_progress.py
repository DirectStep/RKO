from collections.abc import Iterable
from decimal import Decimal

from app.domain.enums import BankInternalStatus
from app.models import LeadBank


FINAL_BANK_STATUSES = {
    BankInternalStatus.ACCOUNT_OPENED,
    BankInternalStatus.NOT_OPENED,
    BankInternalStatus.CUT,
    BankInternalStatus.DUPLICATE,
    BankInternalStatus.BANK_REJECTED,
    BankInternalStatus.CLIENT_REFUSED,
    BankInternalStatus.EXCLUDED,
}
NO_PAYOUT_STATUSES = FINAL_BANK_STATUSES - {BankInternalStatus.ACCOUNT_OPENED}


def application_progress(
    banks: Iterable[LeadBank], *, include_bank_paid_lead_rewards: bool = False,
    not_eligible: bool = False,
) -> dict[str, object]:
    selected = [bank for bank in banks if bank.selected_by_lead is True]
    total = len(selected)
    opened = sum(
        bank.account_opened_at is not None
        or bank.opened_at is not None
        or bank.internal_status is BankInternalStatus.AWAITING_ACTIVATION
        for bank in selected
    )
    activated = sum(bank.opened_at is not None for bank in selected)
    expected = sum(
        (
            bank.lead_reward_estimate or Decimal("0")
            for bank in selected
            if bank.lead_reward_paid_at is None
            and bank.internal_status not in NO_PAYOUT_STATUSES
            and (include_bank_paid_lead_rewards or not bank.lead_reward_paid_separately)
        ),
        Decimal("0"),
    )
    confirmed = sum(
        (
            bank.lead_reward_fact or Decimal("0")
            for bank in selected
            if bank.lead_reward_paid_at is not None
        ),
        Decimal("0"),
    )
    if not selected:
        status = "questionnaire_ineligible" if not_eligible else "questionnaire_completed"
    elif all(bank.internal_status in FINAL_BANK_STATUSES for bank in selected):
        status = "completed"
    elif all(bank.internal_status is BankInternalStatus.PLANNED for bank in selected):
        status = "banks_selected"
    elif any(
        bank.internal_status is BankInternalStatus.PLANNED
        or bank.internal_status not in FINAL_BANK_STATUSES | {BankInternalStatus.AWAITING_ACTIVATION}
        for bank in selected
    ):
        status = "opening_accounts"
    else:
        status = "activating_accounts"
    return {
        "application_status": status,
        "bank_progress": {
            "opened": opened,
            "activated": activated,
            "total": total,
            "expected_payout": str(expected),
            "confirmed_payout": str(confirmed),
        },
    }
