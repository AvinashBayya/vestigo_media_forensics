from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Transcript(Base):
    """A machine transcript of an artifact's audio (Pass 1, D24).

    Machine-generated, potentially inaccurate, and unverified: it is derived material, never
    evidence, and never replaces or rewrites the original audio, which is only ever read. Exports
    carry it in a separated area. The analyst may edit it; edits are kept beside the machine text,
    never on top of it.
    """

    __tablename__ = "transcripts"
    __table_args__ = (Index("ix_transcripts_artifact_created", "artifact_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"))
    # For a video, the extracted audio track this was read from, so the lineage is explicit.
    derived_file_id: Mapped[str | None] = mapped_column(ForeignKey("derived_files.id"))
    language: Mapped[str | None] = mapped_column(String(16))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    # The model's text, kept verbatim even after the analyst edits.
    text: Mapped[str] = mapped_column(Text)
    # [{"start", "end", "text", "words": [{"word", "start", "end", "probability"}]}]
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # The analyst's corrected text, when they have edited it. Never overwrites `text`.
    edited_text: Mapped[str | None] = mapped_column(Text)
    model: Mapped[dict[str, Any]] = mapped_column(JSON)
    warnings: Mapped[list[str]] = mapped_column(JSON)
    review_state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]
