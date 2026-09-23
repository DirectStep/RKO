from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.integrations.google_sheets import (
    LEAD_REGISTRY_HEADERS,
    GoogleSheetsGateway,
    LeadRegistryRow,
    LeadRegistryRowNotFound,
)
from app.services.lead_registry import expected_payment_date


class FakeWorksheet:
    def __init__(self) -> None:
        self.values: list[list[Any]] = [list(LEAD_REGISTRY_HEADERS)]

    def row_values(self, row: int) -> list[Any]:
        return self.values[row - 1] if len(self.values) >= row else []

    def get_all_values(self) -> list[list[Any]]:
        return [list(row) for row in self.values]

    def append_row(self, values: list[Any], value_input_option: str) -> None:
        self.values.append(list(values))

    def update(self, values: list[list[Any]], range_name: str, raw: bool) -> None:
        start = range_name.split(":", maxsplit=1)[0]
        row = int("".join(character for character in start if character.isdigit()))
        while len(self.values) < row:
            self.values.append([])
        if start.startswith("H"):
            current = [*self.values[row - 1], *([""] * 11)]
            current[7:10] = values[0]
            self.values[row - 1] = current[:11]
        else:
            self.values[row - 1] = list(values[0])

    def batch_update(self, changes: list[dict[str, Any]], value_input_option: str) -> None:
        for change in changes:
            row = int(change["range"].removeprefix("C"))
            self.values[row - 1][2] = change["values"][0][0]

    def freeze(self, rows: int) -> None:  # pragma: no cover - formatting only
        pass

    def set_basic_filter(self, name: str) -> None:  # pragma: no cover
        pass

    def format(self, ranges: str, cell_format: dict[str, Any]) -> None:  # pragma: no cover
        pass

    def columns_auto_resize(self, start: int, end: int) -> None:  # pragma: no cover
        pass


class FakeSpreadsheet:
    def __init__(self, worksheet: FakeWorksheet) -> None:
        self._worksheet = worksheet

    def worksheet(self, title: str) -> FakeWorksheet:
        return self._worksheet


def gateway_with(worksheet: FakeWorksheet) -> GoogleSheetsGateway:
    gateway = object.__new__(GoogleSheetsGateway)
    gateway.spreadsheet = FakeSpreadsheet(worksheet)
    return gateway


def registry_row(bank: str = "Альфа-Банк") -> LeadRegistryRow:
    return LeadRegistryRow(
        application_id="RKO-0001",
        activated_at="22.09.2026 21:30",
        lead="@client",
        manager="@manager",
        bank=bank,
        application_status="Счёт активирован",
        expected_payment_at="22.10.2026",
    )


def test_activation_upsert_does_not_create_duplicates_or_reset_payment() -> None:
    worksheet = FakeWorksheet()
    gateway = gateway_with(worksheet)

    gateway.upsert_lead_activation(registry_row())
    gateway.update_lead_payment("RKO-0001", "Альфа-Банк", "22.10.2026 12:00", 5000.0)
    gateway.upsert_lead_activation(registry_row())
    gateway.upsert_lead_activation(registry_row("ВТБ"))
    gateway.upsert_lead_activation(registry_row("ВТБ"))

    assert len(worksheet.values) == 3
    assert [row[4] for row in worksheet.values[1:]] == ["Альфа-Банк", "ВТБ"]
    assert worksheet.values[1][7:10] == ["22.10.2026 12:00", 5000.0, "Выплачено"]
    assert worksheet.values[2][7:10] == ["", "", "Ожидается"]

    gateway.update_lead_payment("RKO-0001", "ВТБ", "23.10.2026 12:00", 2000.0)
    assert worksheet.values[1][8] == 5000.0
    assert worksheet.values[2][7:10] == ["23.10.2026 12:00", 2000.0, "Выплачено"]


def test_payment_update_does_not_create_missing_application() -> None:
    gateway = gateway_with(FakeWorksheet())

    with pytest.raises(LeadRegistryRowNotFound, match="RKO-404"):
        gateway.update_lead_payment("RKO-404", "Альфа-Банк", "22.10.2026 12:00", 5000.0)


def test_payment_does_not_update_another_bank_of_same_application() -> None:
    worksheet = FakeWorksheet()
    gateway = gateway_with(worksheet)
    gateway.upsert_lead_activation(registry_row("Альфа-Банк"))

    with pytest.raises(LeadRegistryRowNotFound, match="ВТБ"):
        gateway.update_lead_payment("RKO-0001", "ВТБ", "22.10.2026 12:00", 5000.0)

    assert worksheet.values[1][7:10] == ["", "", "Ожидается"]


def test_expected_payment_is_exactly_thirty_moscow_calendar_days() -> None:
    activated_at = datetime(2026, 9, 22, 18, 30, tzinfo=UTC)

    assert expected_payment_date(activated_at, ZoneInfo("Europe/Moscow")) == "22.10.2026"


def test_username_sync_updates_each_bank_without_touching_payments() -> None:
    worksheet = FakeWorksheet()
    gateway = gateway_with(worksheet)
    gateway.upsert_lead_activation(registry_row("Альфа-Банк"))
    gateway.upsert_lead_activation(registry_row("ВТБ"))
    gateway.update_lead_payment("RKO-0001", "ВТБ", "23.10.2026 12:00", 2000.0)

    gateway.sync_lead_usernames({"RKO-0001": "@new_client"})
    gateway.sync_lead_usernames({"RKO-0001": "@new_client"})

    assert [row[2] for row in worksheet.values[1:]] == ["@new_client", "@new_client"]
    assert worksheet.values[2][7:10] == ["23.10.2026 12:00", 2000.0, "Выплачено"]
