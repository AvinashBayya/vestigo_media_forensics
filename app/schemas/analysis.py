from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ErrorBody, JobStatus, StageStatus


class DocumentAnalysisOptions(BaseModel):
    """Optional document stages (Pass 2). Hashes always run; nothing in a PDF is ever executed."""

    model_config = ConfigDict(extra="forbid")

    metadata: bool = True
    pdf_structure: bool = True
    pdf_text: bool = True
    pdf_images: bool = True
    structural: bool = True
    duplicate_search: bool = True


class AnalysisOptions(BaseModel):
    """Optional stages. Hashing and the perceptual hash always run (the hash feeds duplicate search)."""

    model_config = ConfigDict(extra="forbid")

    metadata: bool = True
    c2pa: bool = True
    location_clues: bool = True
    structural: bool = True
    forensic_indicators: bool = True
    ocr: bool = True
    duplicate_search: bool = True


class ImageAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)


class VideoAnalysisOptions(BaseModel):
    """Optional video stages. Hashing, media info, keyframes, and the keyframe perceptual hash always
    run. Keyframe OCR is off by default (decision M3-3)."""

    model_config = ConfigDict(extra="forbid")

    metadata: bool = True
    c2pa: bool = True
    location_clues: bool = True
    structural: bool = True
    forensic_indicators: bool = True
    scene_detection: bool = True
    keyframe_ocr: bool = False
    duplicate_search: bool = True


class AudioAnalysisOptions(BaseModel):
    """Optional audio stages (D19). Hashing, media info, and duplicate search by SHA-256 cover the
    rest; no audio is ever decoded."""

    model_config = ConfigDict(extra="forbid")

    metadata: bool = True
    c2pa: bool = True
    location_clues: bool = True
    structural: bool = True
    duplicate_search: bool = True


class AudioAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    options: AudioAnalysisOptions = Field(default_factory=AudioAnalysisOptions)


class DocumentAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    options: DocumentAnalysisOptions = Field(default_factory=DocumentAnalysisOptions)


class VideoAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    options: VideoAnalysisOptions = Field(default_factory=VideoAnalysisOptions)


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


class JobHistoryItem(JobSummary):
    """One analysis run of an artifact (Milestone 2 analysis history)."""

    pipeline: str
    app_version: str
    # The option flags as recorded on the job; keys depend on the pipeline.
    options: dict[str, bool]
    # Job-level failure (e.g. INTERRUPTED by a restart). Stage failures are counted in problem_count.
    error: ErrorBody | None
    # Failed or partial stages, plus one if the job itself failed.
    problem_count: int


class JobHistory(BaseModel):
    artifact_id: str
    # Newest first.
    jobs: list[JobHistoryItem]
