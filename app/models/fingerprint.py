from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ImageFingerprint(Base):
    """Index used by duplicate search. Holds the perceptual hash from the artifact's latest job."""

    __tablename__ = "image_fingerprints"

    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True)
    algorithm: Mapped[str] = mapped_column(String(32), primary_key=True)
    value_hex: Mapped[str] = mapped_column(String(64))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_records.id", ondelete="CASCADE"))
    created_at: Mapped[datetime]
