from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExternalLead(Base):
    """One externally found result, recorded by the analyst (M5).

    A lead is an analyst statement, not a machine observation: URLs and the claimed publication
    date are stored exactly as entered and are never verified by Vestigo. Classification is always
    EXTERNAL. Leads are editable — every create, update, and delete is recorded as an append-only
    custody event (lead_recorded / lead_updated / lead_deleted).
    """

    __tablename__ = "external_leads"
    __table_args__ = (Index("ix_external_leads_artifact_created", "artifact_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"))
    # The searched keyframe for video subjects; NULL when the original image was the subject.
    derived_file_id: Mapped[str | None] = mapped_column(ForeignKey("derived_files.id"))
    provider: Mapped[str] = mapped_column(String(100))
    result_url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    # Analyst-reported, stored as entered, always labelled unverified. Distinct from created_at.
    claimed_published_at: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str] = mapped_column(Text)
    review_state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]
