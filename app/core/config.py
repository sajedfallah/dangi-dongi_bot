from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Dongi"
    env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./dongi.db"
    telegram_bot_token: str = ""
    api_base_url: str = "http://127.0.0.1:8000"
    app_secret_key: str = "change-me-in-production"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
