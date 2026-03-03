"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/checker"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://postgres:postgres@db:5432/checker"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Storage
    STORAGE_DIR: str = "/app/storage"

    # App
    SECRET_KEY: str = "dev-secret-change-me"
    DEBUG: bool = False

    # Server
    PORT: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
