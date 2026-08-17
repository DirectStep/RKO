from enum import StrEnum


class UserRole(StrEnum):
    LEAD = "lead"
    PARTNER = "partner"
    MANAGER = "manager"
    ADMIN = "admin"


class AccessStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class AssignmentStatus(StrEnum):
    UNRESOLVED = "unresolved"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DIRECT = "direct"


class LeadInternalStatus(StrEnum):
    NEW = "new"
    MANAGER_ASSIGNED = "manager_assigned"
    AWAITING_FIRST_CONTACT = "awaiting_first_contact"
    CONTACTED = "contacted"
    AWAITING_DATA = "awaiting_data"
    DATA_RECEIVED = "data_received"
    SELECTING_BANKS = "selecting_banks"
    PREPARING_APPLICATIONS = "preparing_applications"
    APPLICATIONS_SENT = "applications_sent"
    OPENING_ACCOUNTS = "opening_accounts"
    PARTIALLY_OPENED = "partially_opened"
    ALL_PLANNED_OPENED = "all_planned_opened"
    PAUSED = "paused"
    NO_RESPONSE = "no_response"
    LEAD_REFUSED = "lead_refused"
    NOT_ELIGIBLE = "not_eligible"
    COMPLETED = "completed"


class LeadExternalStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    OPENING_ACCOUNTS = "opening_accounts"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    PAUSED = "paused"
    CLOSED_WITHOUT_RESULT = "closed_without_result"


class BankInternalStatus(StrEnum):
    PLANNED = "planned"
    AWAITING_DATA = "awaiting_data"
    PREPARING_APPLICATION = "preparing_application"
    APPLICATION_SENT = "application_sent"
    UNDER_REVIEW = "under_review"
    REVISION_REQUIRED = "revision_required"
    ACCOUNT_OPENED = "account_opened"
    BANK_REJECTED = "bank_rejected"
    CLIENT_REFUSED = "client_refused"
    EXCLUDED = "excluded"


class BankExternalStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    OPENED = "opened"
    NOT_OPENED = "not_opened"
    WILL_NOT_OPEN = "will_not_open"


class PaymentStatus(StrEnum):
    NOT_CALCULATED = "not_calculated"
    CALCULATED = "calculated"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    IN_REGISTRY = "in_registry"
    PAID = "paid"
    CANCELLED = "cancelled"
