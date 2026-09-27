from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.enums import UserRole
from app.domain.operations import DomainError
from app.services.admin_catalog import AdminCatalogService


@pytest.mark.parametrize(
    ("value", "expected"),
    [("15", Decimal("15.00")), ("12,5", Decimal("12.50")), ("0", Decimal("0.00"))],
)
def test_parse_commission(value: str, expected: Decimal) -> None:
    assert AdminCatalogService.parse_commission(value) == expected


@pytest.mark.parametrize("value", ["", "сто", "-1", "100.01", "NaN", "Infinity"])
def test_parse_commission_rejects_invalid_values(value: str) -> None:
    with pytest.raises(DomainError):
        AdminCatalogService.parse_commission(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("@gerasimov", "gerasimov"), (" partner_01 ", "partner_01"), ("нет", None), ("-", None)],
)
def test_parse_telegram_username(value: str, expected: str | None) -> None:
    assert AdminCatalogService.parse_telegram_username(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "@партнер", "name with space", "a" * 33])
def test_parse_telegram_username_rejects_invalid_values(value: str) -> None:
    with pytest.raises(DomainError):
        AdminCatalogService.parse_telegram_username(value)


@pytest.mark.asyncio
async def test_restore_partner_reenables_existing_partner() -> None:
    partner = SimpleNamespace(id=uuid4(), active=False)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def begin(self):
            return self

        async def scalar(self, _query):
            return partner

    service = AdminCatalogService(SimpleNamespace(session=Session))
    restored = await service.restore_partner(actor_role=UserRole.ADMIN, partner_id=partner.id)

    assert restored is partner
    assert partner.active is True
    with pytest.raises(DomainError, match="уже активен"):
        await service.restore_partner(actor_role=UserRole.ADMIN, partner_id=partner.id)
    with pytest.raises(DomainError, match="администратору"):
        await service.restore_partner(actor_role=UserRole.PARTNER, partner_id=partner.id)
