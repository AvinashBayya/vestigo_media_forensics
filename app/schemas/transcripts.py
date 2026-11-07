"""Transcript schemas (Pass 1, D24). Machine-generated, unverified, never evidence."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import ReviewState

TRANSCRIPTS_NOTICE = (
    "Machine-generated transcript: produced by a local speech-to-text model, potentially "
    "inaccurate, and unverified. It is derived material for the analyst to check against the "
    "audio, never evidence in itself, and the original audio is unchanged. Timings come from the "
    "model and can drift; names and unusual words are often wrong."
)


class TranscriptSegmentInfo(BaseModel):
    start: float
    end: float
    text: str
    # Word-level timing with the model's own probabilities, where it provides them.
    words: list[dict[str, Any]] = []


class TranscriptCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # An ISO-639 code to force a language, or omitted to let the model decide.
    language: str | None = Field(default=None, max_length=16)


class TranscriptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The analyst's corrected text. Stored beside the model's, never over it.
    edited_text: str | None = Field(default=None, max_length=500_000)
    review_state: ReviewState | None = None

    @model_validator(mode="after")
    def _no_null_review_state(self) -> "TranscriptUpdate":
        if "review_state" in self.model_fields_set and self.review_state is None:
            raise ValueError("review_state cannot be null; omit it to leave it unchanged.")
        return self


class TranscriptInfo(BaseModel):
    transcript_id: str
    artifact_id: str
    # The extracted audio track this was read from, for videos.
    derived_file_id: str | None
    language: str | None
    duration_seconds: float | None
    # The model's text, kept verbatim.
    text: str
    edited_text: str | None
    segments: list[TranscriptSegmentInfo]
    model: dict
    warnings: list[str] = []
    review_state: ReviewState
    created_at: datetime
    updated_at: datetime | None


class TranscriptsResponse(BaseModel):
    artifact_id: str
    notice: str = TRANSCRIPTS_NOTICE
    transcripts: list[TranscriptInfo]
