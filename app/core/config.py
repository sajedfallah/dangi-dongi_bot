from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "dangi-dongi"
    env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./dongi.db"
    telegram_bot_token: str = ""
    api_base_url: str = "http://127.0.0.1:8000"
    mini_app_url: str = ""
    app_secret_key: str = "change-me-in-production"
    service_api_token: str = "change-me-service-token"
    api_auth_required: bool = True
    telegram_init_data_max_age_seconds: int = 86400
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    free_owned_group_limit: int = 2
    cors_origins: list[str] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]
        return value

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
