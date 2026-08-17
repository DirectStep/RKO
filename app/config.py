from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr
    database_url: str = "postgresql+asyncpg://rko:rko@localhost:5432/rko"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    project_timezone: str = "Europe/Moscow"
    admin_telegram_ids: str = ""
    google_sheet_id: str = ""
    google_service_account_file: str = ""
    sheets_sync_interval_seconds: int = 180

    @property
    def admin_ids(self) -> frozenset[str]:
        return frozenset(
            item.strip() for item in self.admin_telegram_ids.split(",") if item.strip().isdigit()
        )

    @property
    def sheets_enabled(self) -> bool:
        return bool(self.google_sheet_id and self.google_service_account_file)


@lru_cache
def get_settings() -> Settings:
    return Settings()
