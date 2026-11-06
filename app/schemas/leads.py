"""External leads (M5): results the analyst found on external search providers.

A lead is an analyst statement, not a machine observation. URLs and the claimed publication date
are stored exactly as entered and never verified by Vestigo; `recorded_at` (set by Vestigo) and the
analyst-reported publication date are separate facts. Classification is always EXTERNAL.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.schemas.common import ReviewState

LEADS_NOTICE = (
    "External leads are analyst statements: the result URL, image URL, and any publication date "
    "are recorded exactly as the analyst entered them and are not verified by Vestigo. 'Recorded' "
    "is when the lead was saved here; a publication date is analyst-reported and unverified. An "
    "earlier-dated result is a lead about prior appearance, never proof of the original source."
)


def _http_url(value: str) -> str:
    # Stored exactly as entered; only the scheme is checked so a lead is always a web link.
    if not value.startswith(("http://", "https://")):
        raise ValueError("Must be an http:// or https:// URL.")
    return value


HttpUrlText = Annotated[str, Field(min_length=10, max_length=2000), AfterValidator(_http_url)]


class ExternalLeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    result_url: HttpUrlText
    image_url: HttpUrlText | None = None
    # Analyst-reported, stored as entered, always labelled unverified.
    claimed_published_at: str | None = Field(default=None, max_length=100)
    notes: str = Field(default="", max_length=10_000)
    # The searched keyframe for a video subject; omitted when the original image was the subject.
    derived_file_id: str | None = None


class ExternalLeadUpdate(BaseModel):
    """Any subset of the editable lead fields. Every actual change is a custody event."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(default=None, min_length=1, max_length=100)
    result_url: HttpUrlText | None = None
    image_url: HttpUrlText | None = None
    claimed_published_at: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=10_000)
    review_state: ReviewState | None = None


class ExternalLeadInfo(BaseModel):
    lead_id: str
    artifact_id: str
    derived_file_id: str | None
    provider: str
    result_url: str
    image_url: str | None
    # Exactly as the analyst entered it: analyst-reported, unverified.
    claimed_published_at: str | None
    notes: str
    classification: Literal["EXTERNAL"] = "EXTERNAL"
    review_state: ReviewState
    # When Vestigo saved the lead - not when anything was published.
    recorded_at: datetime
    updated_at: datetime | None


class ExternalLeadsResponse(BaseModel):
    artifact_id: str
    notice: str = LEADS_NOTICE
    # Newest first.
    leads: list[ExternalLeadInfo]
