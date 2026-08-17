import pytest

from app.domain.enums import UserRole
from app.domain.permissions import Action, can_access_partner_resource, is_allowed


@pytest.mark.parametrize("action", [Action.CONFIRM_SOURCE, Action.CONFIRM_PAYMENT])
def test_only_admin_can_confirm_critical_operations(action: Action) -> None:
    assert is_allowed(UserRole.ADMIN, action)
    assert not is_allowed(UserRole.MANAGER, action)
    assert not is_allowed(UserRole.PARTNER, action)
    assert not is_allowed(UserRole.LEAD, action)


def test_manager_can_update_leads_but_not_manage_partners() -> None:
    assert is_allowed(UserRole.MANAGER, Action.UPDATE_LEAD)
    assert not is_allowed(UserRole.MANAGER, Action.MANAGE_PARTNERS)


def test_partner_resource_access_is_scoped_by_partner_id() -> None:
    assert can_access_partner_resource(UserRole.PARTNER, "partner-1", "partner-1")
    assert not can_access_partner_resource(UserRole.PARTNER, "partner-1", "partner-2")
    assert can_access_partner_resource(UserRole.ADMIN, None, "partner-2")
