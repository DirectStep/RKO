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
