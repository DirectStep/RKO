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

    @property
    def admin_ids(self) -> frozenset[str]:
        return frozenset(
            item.strip() for item in self.admin_telegram_ids.split(",") if item.strip().isdigit()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
