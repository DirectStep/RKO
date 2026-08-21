from functools import lru_cache
from pathlib import Path
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
    admin_telegram_usernames: str = ""
    admin_group_chat_id: str = ""
    mini_app_url: str = "http://localhost:8090"
    mini_app_host: str = "0.0.0.0"
    mini_app_port: int = 8090
    mini_app_dev_telegram_id: str = ""
    google_sheet_id: str = ""
    bank_conditions_sheet_id: str = ""
    bank_conditions_worksheet: str = "Условия активации"
    google_service_account_file: str = ""
    sheets_sync_interval_seconds: int = 10
    bank_conditions_sync_interval_seconds: int = 60

    @property
    def admin_ids(self) -> frozenset[str]:
        return frozenset(
            item.strip() for item in self.admin_telegram_ids.split(",") if item.strip().isdigit()
        )

    @property
    def admin_usernames(self) -> frozenset[str]:
        return frozenset(
            item.strip().lstrip("@").lower()
            for item in self.admin_telegram_usernames.split(",")
            if item.strip().lstrip("@")
        )

    @property
    def admin_group_id(self) -> int | None:
        value = self.admin_group_chat_id.strip()
        return int(value) if value.lstrip("-").isdigit() else None

    @property
    def sheets_enabled(self) -> bool:
        return bool(
            self.google_sheet_id
            and self.google_service_account_file
            and Path(self.google_service_account_file).is_file()
        )

    @property
    def bank_conditions_enabled(self) -> bool:
        return bool(
            self.bank_conditions_sheet_id
            and self.google_service_account_file
            and Path(self.google_service_account_file).is_file()
        )

    @property
    def mini_app_local_user_id(self) -> str:
        if self.app_env != "development":
            return ""
        return self.mini_app_dev_telegram_id or next(iter(self.admin_ids), "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
