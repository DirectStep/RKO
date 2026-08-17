from app.domain.enums import (
    BankExternalStatus,
    BankInternalStatus,
    LeadExternalStatus,
    LeadInternalStatus,
)

LEAD_STATUS_MAP = {
    LeadInternalStatus.NEW: LeadExternalStatus.NEW,
    LeadInternalStatus.MANAGER_ASSIGNED: LeadExternalStatus.NEW,
    LeadInternalStatus.AWAITING_FIRST_CONTACT: LeadExternalStatus.NEW,
    LeadInternalStatus.CONTACTED: LeadExternalStatus.IN_PROGRESS,
    LeadInternalStatus.AWAITING_DATA: LeadExternalStatus.IN_PROGRESS,
    LeadInternalStatus.DATA_RECEIVED: LeadExternalStatus.IN_PROGRESS,
    LeadInternalStatus.SELECTING_BANKS: LeadExternalStatus.IN_PROGRESS,
    LeadInternalStatus.PREPARING_APPLICATIONS: LeadExternalStatus.OPENING_ACCOUNTS,
    LeadInternalStatus.APPLICATIONS_SENT: LeadExternalStatus.OPENING_ACCOUNTS,
    LeadInternalStatus.OPENING_ACCOUNTS: LeadExternalStatus.OPENING_ACCOUNTS,
    LeadInternalStatus.PARTIALLY_OPENED: LeadExternalStatus.PARTIALLY_COMPLETED,
    LeadInternalStatus.ALL_PLANNED_OPENED: LeadExternalStatus.COMPLETED,
    LeadInternalStatus.PAUSED: LeadExternalStatus.PAUSED,
    LeadInternalStatus.NO_RESPONSE: LeadExternalStatus.PAUSED,
    LeadInternalStatus.LEAD_REFUSED: LeadExternalStatus.CLOSED_WITHOUT_RESULT,
    LeadInternalStatus.NOT_ELIGIBLE: LeadExternalStatus.CLOSED_WITHOUT_RESULT,
    LeadInternalStatus.COMPLETED: LeadExternalStatus.COMPLETED,
}

BANK_STATUS_MAP = {
    BankInternalStatus.PLANNED: BankExternalStatus.PLANNED,
    BankInternalStatus.AWAITING_DATA: BankExternalStatus.IN_PROGRESS,
    BankInternalStatus.PREPARING_APPLICATION: BankExternalStatus.IN_PROGRESS,
    BankInternalStatus.APPLICATION_SENT: BankExternalStatus.IN_PROGRESS,
    BankInternalStatus.UNDER_REVIEW: BankExternalStatus.IN_PROGRESS,
    BankInternalStatus.REVISION_REQUIRED: BankExternalStatus.IN_PROGRESS,
    BankInternalStatus.ACCOUNT_OPENED: BankExternalStatus.OPENED,
    BankInternalStatus.BANK_REJECTED: BankExternalStatus.NOT_OPENED,
    BankInternalStatus.CLIENT_REFUSED: BankExternalStatus.NOT_OPENED,
    BankInternalStatus.EXCLUDED: BankExternalStatus.WILL_NOT_OPEN,
}


def external_lead_status(status: LeadInternalStatus) -> LeadExternalStatus:
    return LEAD_STATUS_MAP[status]


def external_bank_status(status: BankInternalStatus) -> BankExternalStatus:
    return BANK_STATUS_MAP[status]
