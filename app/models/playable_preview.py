from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlayablePreview(Base):
    """A re-encoded viewing copy of a video the browser cannot play (D19). A viewing aid, not
    evidence: excluded from the evidence package, and deleted with the artifact."""

    __tablename__ = "playable_previews"

    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True)
    stored_path: Mapped[str] = mapped_column(String(255), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    width: Mapped[int | None]
    height: Mapped[int | None]
    created_at: Mapped[datetime]
