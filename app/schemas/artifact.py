from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.analysis import JobSummary
from app.schemas.common import JobStatus, MediaType, ReviewState


class ArtifactUploadResponse(BaseModel):
    artifact_id: str
    filename: str
    size_bytes: int
    media_type: MediaType
    mime_type: str
    sha256: str
    created_at: datetime


class ReviewInfo(BaseModel):
    state: ReviewState
    analyst_notes: str
    updated_at: datetime


class ArtifactSummary(BaseModel):
    artifact_id: str
    filename: str
    media_type: MediaType
    mime_type: str
    size_bytes: int
    created_at: datetime
    # Container-reported duration for videos (decision M3-8); None for images.
    duration_seconds: float | None = None
    review_state: ReviewState
    latest_job_status: JobStatus | None


class ArtifactListItem(ArtifactSummary):
    """An artifact with status indicators for its latest analysis job (see app/services/library.py)."""

    latest_job: JobSummary | None
    # Failed or partial stages in the latest job, plus one if the job itself failed. None if never analysed.
    problem_count: int | None
    # Matches in the latest job's duplicate search. None if that search produced no result.
    duplicate_match_count: int | None
    # Artifacts in the duplicate library uploaded after that search finished. None if no search result.
    added_since_analysis: int | None
    in_duplicate_library: bool


class ArtifactDetail(ArtifactListItem):
    sha256: str
    md5: str
    width: int | None
    height: int | None
    # True when a re-encoded viewing copy exists (D19); videos only.
    has_playable_preview: bool = False
    review: ReviewInfo


class ArtifactList(BaseModel):
    items: list[ArtifactListItem]
    total: int
    limit: int
    offset: int
    # Matching artifacts per review state, ignoring the review-state and archive filters.
    counts_by_review_state: dict[ReviewState, int]


class AnalysisStatusFilter(StrEnum):
    QUEUED = JobStatus.QUEUED.value
    RUNNING = JobStatus.RUNNING.value
    COMPLETED = JobStatus.COMPLETED.value
    COMPLETED_WITH_ERRORS = JobStatus.COMPLETED_WITH_ERRORS.value
    FAILED = JobStatus.FAILED.value
    NOT_ANALYSED = "not_analysed"


class ArtifactSort(StrEnum):
    CREATED_AT = "created_at"
    FILENAME = "filename"
    SIZE_BYTES = "size_bytes"
    REVIEW_STATE = "review_state"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


SupportedMimeType = Literal[
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff",
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "video/x-msvideo",
    "video/mp2t",
    "video/x-ms-wmv",
    "video/x-flv",
    "video/3gpp",
    "video/x-m4v",
    "video/ogg",
    "audio/wav",
    "audio/mpeg",
    "audio/flac",
    "audio/ogg",
    "audio/mp4",
]


class ArtifactQuery(BaseModel):
    """Query parameters of GET /artifacts. Every parameter is optional; unknown parameters are rejected."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(None, max_length=200)
    review_state: list[ReviewState] = []
    analysis_status: list[AnalysisStatusFilter] = []
    has_problems: bool | None = None
    has_duplicates: bool | None = None
    mime_type: list[SupportedMimeType] = []
    uploaded_from: AwareDatetime | None = None
    uploaded_to: AwareDatetime | None = None
    # True keeps the Milestone 1 behaviour of listing every artifact; the Library sends false.
    include_archived: bool = True
    sort: ArtifactSort = ArtifactSort.CREATED_AT
    order: SortOrder = SortOrder.DESC
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)

    @field_validator("q")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def _date_range(self) -> Self:
        if self.uploaded_from and self.uploaded_to and self.uploaded_from > self.uploaded_to:
            raise ValueError("uploaded_from must not be later than uploaded_to.")
        return self


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ReviewState
    analyst_notes: str = Field("", max_length=20_000)
    # The review's updated_at as last seen. If sent and the review has changed since, the update is
    # refused with REVIEW_CONFLICT (409) instead of overwriting the newer review.
    expected_updated_at: AwareDatetime | None = None


class DeletionSummary(BaseModel):
    artifact_id: str
    original_files: int
    derived_files: int
    jobs: int
    evidence_records: int
    review_events: int = 0
    preview_files: int = 0
    custody_events: int = 0
    external_leads: int = 0
    location_candidates: int = 0
    ai_drafts: int = 0
    transcripts: int = 0
    embedding_chunks: int = 0


class PreviewInfo(BaseModel):
    """A re-encoded viewing copy of a video (D19). Not evidence; excluded from the export package."""

    artifact_id: str
    sha256: str
    size_bytes: int
    width: int | None
    height: int | None
    created_at: datetime
