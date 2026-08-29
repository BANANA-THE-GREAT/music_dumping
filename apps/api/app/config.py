from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VSS_", env_file=".env", extra="ignore")

    environment: str = "development"
    api_title: str = "Vocal Score Studio API"
    api_version: str = "0.1.0"
    cors_origins: list[str] = ["http://localhost:4173", "http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
