from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    secret_key: str = "dev-secret-change-in-production"
    admin_email: str = "admin@example.com"
    database_url: str = "sqlite:///./padel.db"
    elo_k: float = 24.0
    default_rating: float = 1000.0
    session_max_age_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()

