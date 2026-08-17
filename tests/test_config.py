from app.config import Settings


def test_settings_accept_required_token() -> None:
    settings = Settings(bot_token="123456:test-token", app_env="test")

    assert settings.app_env == "test"
    assert settings.bot_token.get_secret_value() == "123456:test-token"
    assert "test-token" not in repr(settings)
    assert settings.project_timezone == "Europe/Moscow"
    assert settings.database_url.startswith("postgresql+asyncpg://")
