from enum import StrEnum

from app.domain.enums import UserRole


class Action(StrEnum):
    SUBMIT_APPLICATION = "submit_application"
    VIEW_OWN_CHANNELS = "view_own_channels"
    VIEW_OWN_LEADS = "view_own_leads"
    VIEW_OWN_PAYMENTS = "view_own_payments"
    CONTACT_MANAGER = "contact_manager"
    MANAGE_USERS = "manage_users"
    MANAGE_PARTNERS = "manage_partners"
    MANAGE_DICTIONARIES = "manage_dictionaries"
    ASSIGN_MANAGER = "assign_manager"
    CONFIRM_SOURCE = "confirm_source"
    VIEW_ALL_LEADS = "view_all_leads"
    UPDATE_LEAD = "update_lead"
    MANAGE_LEAD_BANKS = "manage_lead_banks"
    VIEW_BANK_INCOME = "view_bank_income"
    CONFIRM_PAYMENT = "confirm_payment"
    CHANGE_PAYMENT_STATUS = "change_payment_status"
    DELETE_LEAD = "delete_lead"
    EXPORT_PARTNER_REPORT = "export_partner_report"
    EXPORT_ADMIN_REPORT = "export_admin_report"


ROLE_ACTIONS: dict[UserRole, frozenset[Action]] = {
    UserRole.LEAD: frozenset({Action.SUBMIT_APPLICATION}),
    UserRole.PARTNER: frozenset(
        {
            Action.VIEW_OWN_CHANNELS,
            Action.VIEW_OWN_LEADS,
            Action.VIEW_OWN_PAYMENTS,
            Action.CONTACT_MANAGER,
            Action.EXPORT_PARTNER_REPORT,
        }
    ),
    UserRole.MANAGER: frozenset(
        {
            Action.VIEW_ALL_LEADS,
            Action.UPDATE_LEAD,
            Action.MANAGE_LEAD_BANKS,
            Action.VIEW_BANK_INCOME,
            Action.DELETE_LEAD,
        }
    ),
    UserRole.ADMIN: frozenset(Action),
}


def is_allowed(role: UserRole, action: Action) -> bool:
    return action in ROLE_ACTIONS[role]


def can_access_partner_resource(
    role: UserRole, user_partner_id: str | None, resource_partner_id: str
) -> bool:
    if role in {UserRole.ADMIN, UserRole.MANAGER}:
        return True
    return role is UserRole.PARTNER and user_partner_id == resource_partner_id
