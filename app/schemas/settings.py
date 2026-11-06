"""Basic local settings (decision M2-8).

Editable settings are stored in SQLite. Environment settings come from VESTIGO_* variables or .env and
are read-only here: they include security limits and the duplicate threshold, which is recorded in
every duplicate-search result.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.schemas.analysis import AnalysisOptions, AudioAnalysisOptions, VideoAnalysisOptions
from app.services.search_providers import PROVIDER_KEYS

LibraryPageSize = Literal[10, 25, 50, 100]


def _known_provider_keys(keys: list[str]) -> list[str]:
    unknown = sorted(set(keys) - PROVIDER_KEYS)
    if unknown:
        raise ValueError(f"Unknown search provider(s): {', '.join(unknown)}.")
    return sorted(set(keys))


# Registry keys only, deduplicated; validated the same way for API updates and stored values.
EnabledSearchProviders = Annotated[list[str], AfterValidator(_known_provider_keys)]


class EditableSettings(BaseModel):
    # Used for new analyses when no options are given, and as the upload page's defaults.
    default_analysis_options: AnalysisOptions = Field(default_factory=AnalysisOptions)
    default_video_analysis_options: VideoAnalysisOptions = Field(default_factory=VideoAnalysisOptions)
    default_audio_analysis_options: AudioAnalysisOptions = Field(default_factory=AudioAnalysisOptions)
    library_page_size: LibraryPageSize = 25
    # Start the analysis as soon as an upload finishes.
    auto_analyze_after_upload: bool = True
    # Reverse-image search providers the analyst has enabled (M5). All disabled by default (05 §4).
    enabled_search_providers: EnabledSearchProviders = Field(default_factory=list)


class EnvironmentSettings(BaseModel):
    data_dir: str
    max_upload_bytes: int
    max_image_pixels: int
    # The pHash Hamming-distance threshold for duplicate matches (read-only in the UI).
    duplicate_threshold: int
    # Video limits (decision M3-2), all read-only here.
    max_video_upload_bytes: int
    max_video_duration_seconds: float
    max_video_pixels: int
    max_keyframes: int
    scene_threshold: float
    video_timeout_seconds: float
    max_audio_upload_bytes: int
    max_audio_duration_seconds: float
    job_mode: str
    job_workers: int
    tool_timeout_seconds: float
    ocr_timeout_seconds: float
    ocr_languages: list[str]
    log_level: str
    app_version: str
    schema_revision: str | None


ENVIRONMENT_KEYS = frozenset(EnvironmentSettings.model_fields) | {"phash_max_distance"}


class SettingsUpdate(BaseModel):
    """Any subset of the editable settings. Environment settings cannot be changed here."""

    model_config = ConfigDict(extra="forbid")

    default_analysis_options: AnalysisOptions | None = None
    default_video_analysis_options: VideoAnalysisOptions | None = None
    default_audio_analysis_options: AudioAnalysisOptions | None = None
    library_page_size: LibraryPageSize | None = None
    auto_analyze_after_upload: bool | None = None
    enabled_search_providers: EnabledSearchProviders | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_environment_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            fixed = sorted(ENVIRONMENT_KEYS & set(data))
            if fixed:
                raise ValueError(
                    f"{', '.join(fixed)} cannot be changed here: set it in the environment (.env) and "
                    "restart the backend."
                )
        return data


class SettingsResponse(BaseModel):
    editable: EditableSettings
    environment: EnvironmentSettings
    # When an editable setting was last changed; None if all are at their defaults.
    updated_at: datetime | None
