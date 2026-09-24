from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.config import Settings
from app.integrations.google_sheets import GoogleSheetsGateway, SheetData
from app.services.sheets_snapshot import SHEET_MODELS, serialize_cell


def test_sheets_are_disabled_without_id_and_credentials() -> None:
    settings = Settings(bot_token="123456:test-token")

    assert settings.sheets_enabled is False


def test_sheets_sync_checks_for_changes_every_ten_seconds() -> None:
    settings = Settings(bot_token="123456:test-token")

    assert settings.sheets_sync_interval_seconds == 10


def test_sheets_are_enabled_with_existing_credentials_file(tmp_path) -> None:
    credentials_file = tmp_path / "service-account.json"
    credentials_file.write_text("{}", encoding="utf-8")
    settings = Settings(
        bot_token="123456:test-token",
        google_sheet_id="sheet-id",
        google_service_account_file=str(credentials_file),
    )

    assert settings.sheets_enabled is True


def test_sheet_model_names_are_stable() -> None:
    assert [title for title, _ in SHEET_MODELS] == [
        "Пользователи",
        "Партнёры",
        "Каналы",
        "Заявки",
        "Банки",
        "Ставки банков",
        "Банки заявок",
        "Выплаты",
        "Проверка дублей",
    ]


def test_sheet_cell_serialization() -> None:
    assert serialize_cell(UUID("8a124766-93ec-4e02-9c85-2260ebad0422")) == (
        "8a124766-93ec-4e02-9c85-2260ebad0422"
    )
    assert serialize_cell(Decimal("12.50")) == "12.50"
    assert serialize_cell(datetime(2026, 8, 17, 12, 0, tzinfo=UTC)) == "2026-08-17T12:00:00+00:00"
    assert serialize_cell({"city": "Москва"}) == '{"city": "Москва"}'


def test_existing_sheet_expands_for_new_snapshot_columns() -> None:
    class Worksheet:
        title = "Заявки"
        row_count = 2
        col_count = 1

        def resize(self, *, rows: int, cols: int) -> None:
            self.row_count, self.col_count = rows, cols

        def clear(self) -> None:
            pass

        def update(self, values: list[list[str]], cell: str, *, raw: bool) -> None:
            assert cell == "A1" and raw
            assert values == [["id", "partner_percent_snapshot"], ["1", "20"]]
            assert self.row_count >= len(values)
            assert self.col_count >= len(values[0])

        def freeze(self, *, rows: int) -> None:
            assert rows == 1

    class Spreadsheet:
        def worksheets(self) -> list[Worksheet]:
            return [worksheet]

    worksheet = Worksheet()
    gateway = object.__new__(GoogleSheetsGateway)
    gateway.spreadsheet = Spreadsheet()
    gateway.replace_all(
        [SheetData("Заявки", ("id", "partner_percent_snapshot"), [["1", "20"]])]
    )
    assert worksheet.col_count == 2
