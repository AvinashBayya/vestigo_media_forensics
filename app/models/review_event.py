from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReviewEvent(Base):
    """One analyst review change (decision M2-3). Append-only: the database rejects updates and deletes,
    except the cascade when the artifact itself is deleted."""

    __tablename__ = "review_events"
    __table_args__ = (Index("ix_review_events_artifact_created", "artifact_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"))
    # Set for a change to one evidence record; NULL for a change to the artifact's own review.
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence_records.id", ondelete="CASCADE"))
    # "artifact", "record", or "bulk".
    origin: Mapped[str] = mapped_column(String(16))
    from_state: Mapped[str] = mapped_column(String(16))
    to_state: Mapped[str] = mapped_column(String(16))
    notes_before: Mapped[str] = mapped_column(Text)
    notes_after: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]
