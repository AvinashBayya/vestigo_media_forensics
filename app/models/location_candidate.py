from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LocationCandidate(Base):
    """One possible location, stated by the analyst (M6).

    A candidate is an analyst interpretation of Vestigo-held evidence, classified UNVERIFIED: the
    description, coordinates, basis, and assessment are the analyst's own statements, never machine
    conclusions. Candidates are editable — every create, update, and delete is recorded as an
    append-only custody event (location_candidate_recorded / _updated / _deleted).
    """

    __tablename__ = "location_candidates"
    __table_args__ = (Index("ix_location_candidates_artifact_created", "artifact_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"))
    # The place as the analyst would state it, e.g. "Near Trafalgar Square, London".
    description: Mapped[str] = mapped_column(String(500))
    # Optional analyst-entered coordinates, range-validated on input and stored as given.
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    # Why the analyst thinks so - required, in their own words.
    basis: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text)
    # "speculative" | "possible" | "likely": the analyst's own judgment, never machine-derived.
    analyst_assessment: Mapped[str] = mapped_column(String(16))
    # Typed references to supporting evidence of the SAME artifact:
    # [{"type": "evidence_record" | "derived_file" | "external_lead", "id": "..."}].
    supports: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    review_state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]
