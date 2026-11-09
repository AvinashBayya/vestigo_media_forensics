"""Basic local settings (decision M2-8).

Editable settings are stored in SQLite. Environment settings come from VESTIGO_* variables or .env and
are read-only here: they include security limits and the duplicate threshold, which is recorded in
every duplicate-search result.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.schemas.analysis import (
    AnalysisOptions,
    AudioAnalysisOptions,
    DocumentAnalysisOptions,
    VideoAnalysisOptions,
)
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
    default_document_analysis_options: DocumentAnalysisOptions = Field(
        default_factory=DocumentAnalysisOptions
    )
    library_page_size: LibraryPageSize = 25
    # Start the analysis as soon as an upload finishes.
    auto_analyze_after_upload: bool = True
    # Reverse-image search providers the analyst has enabled (M5). All disabled by default (05 §4).
    enabled_search_providers: EnabledSearchProviders = Field(default_factory=list)
    # Off by default (M6): when on, the artifact page offers an OpenStreetMap link for coordinates
    # found in metadata. The link is built in the browser; the backend never constructs or logs one.
    enable_external_map_links: bool = False
    # Local AI (Pass 1, D24). All off by default: nothing is installed, loaded, or downloaded until
    # the analyst turns a capability on. AI output is never evidence.
    ai_enabled: bool = False
    transcription_enabled: bool = False
    semantic_search_enabled: bool = False
    # Paths to locally held model files (.cact). Empty means "let the runtime resolve its default".
    # Read-only integration surface (Pass 3). Off by default; it can never write anything.
    integration_api_enabled: bool = False
    ai_model_path: str = ""
    transcription_model_path: str = ""


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
    max_document_upload_bytes: int
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
    default_document_analysis_options: DocumentAnalysisOptions | None = None
    library_page_size: LibraryPageSize | None = None
    auto_analyze_after_upload: bool | None = None
    enabled_search_providers: EnabledSearchProviders | None = None
    enable_external_map_links: bool | None = None
    ai_enabled: bool | None = None
    transcription_enabled: bool | None = None
    semantic_search_enabled: bool | None = None
    integration_api_enabled: bool | None = None
    ai_model_path: str | None = Field(default=None, max_length=1000)
    transcription_model_path: str | None = Field(default=None, max_length=1000)

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
