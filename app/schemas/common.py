from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class ReviewState(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    IN_REVIEW = "IN_REVIEW"
    REVIEWED = "REVIEWED"
    FLAGGED = "FLAGGED"
    ARCHIVED = "ARCHIVED"


class EvidenceClassification(StrEnum):
    """Where a piece of evidence came from. Set when the record is created and never changed."""

    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    EXTERNAL = "EXTERNAL"
    UNVERIFIED = "UNVERIFIED"
    REVIEWED = "REVIEWED"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


ACTIVE_JOB_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.RUNNING})


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class ErrorCode(StrEnum):
    MISSING_FILE = "MISSING_FILE"
    EMPTY_FILE = "EMPTY_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    INVALID_IMAGE = "INVALID_IMAGE"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    INVALID_VIDEO = "INVALID_VIDEO"
    INVALID_AUDIO = "INVALID_AUDIO"
    AUDIO_TOO_LONG = "AUDIO_TOO_LONG"
    VIDEO_TOO_LONG = "VIDEO_TOO_LONG"
    VIDEO_RESOLUTION_TOO_LARGE = "VIDEO_RESOLUTION_TOO_LARGE"
    WRONG_MEDIA_TYPE = "WRONG_MEDIA_TYPE"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    ANALYSIS_IN_PROGRESS = "ANALYSIS_IN_PROGRESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    HTTP_ERROR = "HTTP_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INTERRUPTED = "INTERRUPTED"
    REVIEW_CONFLICT = "REVIEW_CONFLICT"
    EVIDENCE_RECORD_NOT_FOUND = "EVIDENCE_RECORD_NOT_FOUND"
    EXPORT_FAILED = "EXPORT_FAILED"
    PREVIEW_FAILED = "PREVIEW_FAILED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    error: ErrorBody
