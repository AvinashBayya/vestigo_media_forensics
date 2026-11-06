from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CustodyEvent(Base):
    """One recorded action in an artifact's chain of custody (M4B).

    Only actions that leave no trace in the existing tables are stored here: evidence-package
    exports, duplicate-library include/exclude changes, and playable-preview creation. Upload,
    analysis jobs, evidence records, and review changes stay in their own tables; the custody
    timeline merges all sources at read time. Append-only: the database rejects updates and
    deletes, except the cascade when the artifact itself is deleted.
    """

    __tablename__ = "custody_events"
    __table_args__ = (Index("ix_custody_events_artifact_created", "artifact_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"))
    # "exported", "library_changed", or "preview_created".
    event_type: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime]
