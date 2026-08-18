from decimal import Decimal

import pytest

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
