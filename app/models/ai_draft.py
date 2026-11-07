from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIDraft(Base):
    """One set of fields a local model proposed from material Vestigo already holds (Pass 1, D24).

    A draft is never evidence: it lives outside the evidence tables, carries no classification, and
    is labelled "AI-generated, unverified - analyst must review" everywhere it appears. The analyst
    accepts, edits, or rejects each field; nothing is ever written back over metadata or evidence.
    """

    __tablename__ = "ai_drafts"
    __table_args__ = (Index("ix_ai_drafts_artifact_created", "artifact_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"))
    # What was asked for, e.g. "field_extraction".
    kind: Mapped[str] = mapped_column(String(32))
    # Which held material the model read: "ocr_text", "analyst_notes", "metadata", "transcript".
    source_kind: Mapped[str] = mapped_column(String(32))
    # The evidence record the text came from, when it came from one. Read-only lineage.
    source_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_records.id", ondelete="SET NULL")
    )
    # [{"name", "value", "confidence"|None, "status": proposed|accepted|edited|rejected, "edited_value"}]
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # Overall draft state, derived from its fields: proposed | reviewed.
    status: Mapped[str] = mapped_column(String(16))
    # Full model provenance: name, version, quantization, source_url, license, runtime, local_path.
    model: Mapped[dict[str, Any]] = mapped_column(JSON)
    reasoning: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]
