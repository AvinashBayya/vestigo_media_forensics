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
    # Video limits (decision M3-2). All read-only in the Settings UI.
    max_video_upload_bytes: int = Field(500 * MIB, gt=0)
    max_video_duration_seconds: float = Field(900.0, gt=0)
    max_video_pixels: int = Field(8_294_400, gt=0)
    max_keyframes: int = Field(40, ge=1, le=500)
    scene_threshold: float = Field(0.3, gt=0, lt=1)
    video_timeout_seconds: float = Field(600.0, gt=0)
    # Audio limits (D19), read-only in the Settings UI.
    max_audio_upload_bytes: int = Field(200 * MIB, gt=0)
    max_audio_duration_seconds: float = Field(7200.0, gt=0)
    # Documents (Pass 2): PDFs are parsed in place, never rendered or executed.
    max_document_upload_bytes: int = Field(100 * MIB, gt=0)

    # Cap on a staged local AI model file. Current models are tens of megabytes; the ceiling is
    # generous so a larger one does not need a code change, and it is separate from evidence limits.
    max_model_bytes: int = Field(1024 * MIB, gt=0)
    # Offline map data the analyst supplies (Pass 3). Vestigo never downloads map data or tiles.
    offline_map_path: str = ""
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
