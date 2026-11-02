from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ErrorBody, JobStatus, StageStatus


class AnalysisOptions(BaseModel):
    """Optional stages. Hashing and the perceptual hash always run (the hash feeds duplicate search)."""

    model_config = ConfigDict(extra="forbid")

    metadata: bool = True
    c2pa: bool = True
    ocr: bool = True
    duplicate_search: bool = True


class ImageAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)


class JobCreated(BaseModel):
    job_id: str
    artifact_id: str
    status: JobStatus


class StageProgress(BaseModel):
    stage: str
    status: StageStatus
    started_at: datetime | None
    completed_at: datetime | None


class JobSummary(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class JobStatusResponse(JobSummary):
    artifact_id: str
    pipeline: str
    error: ErrorBody | None
    stages: list[StageProgress]
