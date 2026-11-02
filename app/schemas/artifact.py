from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
    review_state: ReviewState
    latest_job_status: JobStatus | None


class ArtifactDetail(ArtifactSummary):
    sha256: str
    md5: str
    width: int | None
    height: int | None
    review: ReviewInfo
    latest_job: JobSummary | None


class ArtifactList(BaseModel):
    items: list[ArtifactSummary]
    total: int
    limit: int
    offset: int


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ReviewState
    analyst_notes: str = Field("", max_length=20_000)


class DeletionSummary(BaseModel):
    artifact_id: str
    original_files: int
    derived_files: int
    jobs: int
    evidence_records: int
