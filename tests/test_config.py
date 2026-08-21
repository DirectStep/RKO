from app.config import Settings
from app.database import Database


def test_settings_accept_required_token() -> None:
    settings = Settings(bot_token="123456:test-token", app_env="test")

    assert settings.app_env == "test"
    assert settings.bot_token.get_secret_value() == "123456:test-token"
    assert "test-token" not in repr(settings)
    assert settings.project_timezone == "Europe/Moscow"
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_database_hides_query_parameters_in_errors() -> None:
    settings = Settings(bot_token="123456:test-token", app_env="test")
    database = Database(settings)

    assert database.engine.sync_engine.hide_parameters is True


def test_admin_ids_are_parsed_from_comma_separated_setting() -> None:
    settings = Settings(
        bot_token="123456:test-token",
        admin_telegram_ids="123, 456,not-an-id",
    )

    assert settings.admin_ids == frozenset({"123", "456"})


def test_admin_usernames_are_normalized() -> None:
    settings = Settings(
        bot_token="123456:test-token",
        admin_telegram_usernames=" @XirasS, manager ",
    )

    assert settings.admin_usernames == frozenset({"xirass", "manager"})


def test_admin_group_id_accepts_telegram_supergroup_id() -> None:
    settings = Settings(
        bot_token="123456:test-token",
        admin_group_chat_id="-1001234567890",
    )

    assert settings.admin_group_id == -1001234567890


def test_bank_conditions_are_enabled_with_sheet_and_credentials(tmp_path) -> None:
    credentials_file = tmp_path / "service-account.json"
    credentials_file.write_text("{}", encoding="utf-8")
    settings = Settings(
        bot_token="123456:test-token",
        bank_conditions_sheet_id="conditions-sheet",
        google_service_account_file=str(credentials_file),
    )

    assert settings.bank_conditions_enabled is True
    assert settings.bank_conditions_worksheet == "Условия активации"
    assert settings.bank_conditions_sync_interval_seconds == 60
