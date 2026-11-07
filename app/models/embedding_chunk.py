from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EmbeddingChunk(Base):
    """One indexed chunk of the analyst's own text, with its vector (Pass 1, D24).

    Derived, rebuildable data for local semantic search: analyst notes, OCR text, transcripts, and
    selected metadata. Never sent anywhere, deleted with the artifact, and always recorded with the
    model that produced the vector so an index built by one model is never mixed with another's.
    """

    __tablename__ = "embedding_chunks"
    __table_args__ = (
        Index("ix_embedding_chunks_artifact", "artifact_id"),
        Index("ix_embedding_chunks_model", "model_name"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"))
    # "analyst_notes", "ocr_text", "transcript", "metadata", "location_candidate", "external_lead".
    source_kind: Mapped[str] = mapped_column(String(32))
    # The record the chunk came from, when it has one (evidence id, transcript id, candidate id).
    source_ref: Mapped[str | None] = mapped_column(String(40))
    ordinal: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    vector: Mapped[list[float]] = mapped_column(JSON)
    model_name: Mapped[str] = mapped_column(String(64))
    dimensions: Mapped[int]
    created_at: Mapped[datetime]

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "source_kind": self.source_kind}
