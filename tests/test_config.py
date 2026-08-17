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
