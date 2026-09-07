from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VSS_", env_file=".env", extra="ignore")

    environment: str = "development"
    api_title: str = "Vocal Score Studio API"
    api_version: str = "0.1.0"
    cors_origins: list[str] = [
        "http://localhost:4173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:4174",
        "http://127.0.0.1:5173",
    ]
    data_dir: Path = Path("data")
    database_url: str = "sqlite:///data/vss.db"
    auto_create_schema: bool = True
    max_upload_bytes: int = 200 * 1024 * 1024
    allowed_audio_types: set[str] = {
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/flac",
        "audio/x-flac",
        "audio/mp4",
    }
    worker_backend: str = "thread"
    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    game_model_path: Path = Path("/models/game/GAME-1.0-medium/model.pt")
    game_root: Path = Path("/opt/game")
    torchcrepe_root: Path = Path("/opt/torchcrepe")


@lru_cache
def get_settings() -> Settings:
    return Settings()
