"""Review workflow (decisions M2-2, M2-3, M2-5)."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.common import EvidenceClassification, ReviewState

NOTES_MAX_LENGTH = 20_000
BULK_REVIEW_LIMIT = 200


class RecordReviewUpdate(BaseModel):
    """Review of one evidence record. Never changes the record's classification."""

    model_config = ConfigDict(extra="forbid")

    state: ReviewState
    analyst_notes: str = Field("", max_length=NOTES_MAX_LENGTH)
    # The record's review_updated_at as last seen (null if never reviewed). If sent and the record has
    # changed since, the update is refused with REVIEW_CONFLICT.
    expected_updated_at: AwareDatetime | None = None


class RecordReview(BaseModel):
    evidence_id: str
    artifact_id: str
    job_id: str
    stage: str
    classification: EvidenceClassification
    review_state: ReviewState
    analyst_notes: str
    review_updated_at: datetime | None


class BulkReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_ids: list[str] = Field(min_length=1, max_length=BULK_REVIEW_LIMIT)
    state: ReviewState


class BulkReviewResult(BaseModel):
    state: ReviewState
    # Artifacts whose state changed, and artifacts already in that state (left untouched).
    updated: list[str]
    unchanged: list[str]


class ReviewEventOut(BaseModel):
    event_id: str
    origin: Literal["artifact", "record", "bulk"]
    # Set for record-level events.
    evidence_id: str | None
    stage: str | None
    job_id: str | None
    from_state: ReviewState
    to_state: ReviewState
    notes_before: str
    notes_after: str
    created_at: datetime


class ReviewHistory(BaseModel):
    artifact_id: str
    # Newest first.
    events: list[ReviewEventOut]
