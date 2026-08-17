from app.domain.enums import (
    BankExternalStatus,
    BankInternalStatus,
    LeadExternalStatus,
    LeadInternalStatus,
)
from app.domain.statuses import (
    BANK_STATUS_MAP,
    LEAD_STATUS_MAP,
    external_bank_status,
    external_lead_status,
)


def test_every_internal_lead_status_has_external_mapping() -> None:
    assert set(LEAD_STATUS_MAP) == set(LeadInternalStatus)


def test_every_internal_bank_status_has_external_mapping() -> None:
    assert set(BANK_STATUS_MAP) == set(BankInternalStatus)


def test_sensitive_internal_details_are_collapsed_for_partner() -> None:
    assert external_lead_status(LeadInternalStatus.AWAITING_DATA) == LeadExternalStatus.IN_PROGRESS
    assert (
        external_bank_status(BankInternalStatus.REVISION_REQUIRED) == BankExternalStatus.IN_PROGRESS
    )
