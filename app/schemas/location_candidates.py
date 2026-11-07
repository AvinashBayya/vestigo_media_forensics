"""Location candidates (M6): possible locations stated by the analyst.

A candidate is an analyst interpretation of Vestigo-held evidence, classified UNVERIFIED. The
description, coordinates, basis, and assessment are the analyst's own statements, recorded as
entered and never verified; `recorded_at` (set by Vestigo) is a different fact from anything the
analyst says about when or where the media was made. The assessment label is the analyst's own
judgment, never a machine-derived confidence score.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import ReviewState

CANDIDATES_NOTICE = (
    "Location candidates are analyst statements, classified UNVERIFIED: the place, any coordinates, "
    "the basis, and the assessment are recorded as the analyst entered them and are not verified by "
    "Vestigo. The assessment label is the analyst's own judgment, never a machine-calculated "
    "confidence. A candidate is never a finding that the media was captured at that place."
)

# The analyst's own judgment. No "confirmed": only the review workflow records analyst sign-off,
# and no label may read as a verdict.
AnalystAssessment = Literal["speculative", "possible", "likely"]

# What a candidate may cite as support: evidence of the SAME artifact, checked on input.
SupportType = Literal["evidence_record", "derived_file", "external_lead"]

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class SupportRef(BaseModel):
    """One typed reference to supporting evidence held by Vestigo for this artifact."""

    model_config = ConfigDict(extra="forbid")

    type: SupportType
    id: str = Field(min_length=3, max_length=40)


class LocationCandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    # Why the analyst thinks so, in their own words. Required: a candidate without a basis would be
    # a bare assertion.
    basis: str = Field(min_length=1, max_length=10_000)
    # Required: the analyst always chooses their own assessment; Vestigo never defaults it silently.
    analyst_assessment: AnalystAssessment
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    notes: str = Field(default="", max_length=10_000)
    supports: list[SupportRef] = []

    @model_validator(mode="after")
    def _coordinates_come_in_pairs(self) -> "LocationCandidateCreate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be given together, or both left out.")
        return self


class LocationCandidateUpdate(BaseModel):
    """Any subset of the editable fields. Every actual change is a custody event."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, min_length=1, max_length=500)
    basis: str | None = Field(default=None, min_length=1, max_length=10_000)
    analyst_assessment: AnalystAssessment | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    supports: list[SupportRef] | None = None
    review_state: ReviewState | None = None

    @model_validator(mode="after")
    def _no_null_for_required_fields(self) -> "LocationCandidateUpdate":
        # latitude/longitude may be cleared with an explicit null (together); the rest may not.
        nulled = sorted(
            name
            for name in ("description", "basis", "analyst_assessment", "notes", "supports", "review_state")
            if name in self.model_fields_set and getattr(self, name) is None
        )
        if nulled:
            raise ValueError(f"{', '.join(nulled)} cannot be null; omit the field to leave it unchanged.")
        given = self.model_fields_set
        if ("latitude" in given) != ("longitude" in given):
            raise ValueError("latitude and longitude must be changed together.")
        if "latitude" in given and (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be given together, or both cleared together.")
        return self


class LocationCandidateInfo(BaseModel):
    candidate_id: str
    artifact_id: str
    description: str
    latitude: float | None
    longitude: float | None
    basis: str
    notes: str
    # The analyst's own judgment, never machine-derived.
    analyst_assessment: AnalystAssessment
    supports: list[SupportRef] = []
    classification: Literal["UNVERIFIED"] = "UNVERIFIED"
    review_state: ReviewState
    # When Vestigo saved the candidate - not when anything was captured.
    recorded_at: datetime
    updated_at: datetime | None


class LocationCandidatesResponse(BaseModel):
    artifact_id: str
    notice: str = CANDIDATES_NOTICE
    # Newest first.
    candidates: list[LocationCandidateInfo]
