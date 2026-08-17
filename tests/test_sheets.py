from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.config import Settings
from app.services.sheets_snapshot import SHEET_MODELS, serialize_cell


def test_sheets_are_disabled_without_id_and_credentials() -> None:
    settings = Settings(bot_token="123456:test-token")

    assert settings.sheets_enabled is False


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
