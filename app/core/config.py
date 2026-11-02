"""Application settings, read from VESTIGO_* environment variables and an optional .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MIB = 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VESTIGO_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    max_upload_bytes: int = Field(50 * MIB, gt=0)
    max_image_pixels: int = Field(100_000_000, gt=0)
    phash_max_distance: int = Field(10, ge=0, le=64)
    job_mode: Literal["thread", "inline"] = "thread"
    job_workers: int = Field(2, ge=1)
    tool_timeout_seconds: float = Field(60.0, gt=0)
    ocr_timeout_seconds: float = Field(120.0, gt=0)
    cors_origins: list[str] = ["http://localhost:5180", "http://127.0.0.1:5180"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
