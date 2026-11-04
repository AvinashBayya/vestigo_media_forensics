from datetime import datetime

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KeyframeFingerprint(Base):
    """Perceptual hashes of a video's selected keyframes, from the artifact's latest successful
    analysis (Milestone 3). Used by duplicate search across videos and images; replaced when the
    video is analysed again, and deleted with the artifact."""

    __tablename__ = "keyframe_fingerprints"

    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True)
    algorithm: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Selection order of the keyframe within its analysis (1-based).
    frame_seq: Mapped[int] = mapped_column(primary_key=True)
    timestamp_seconds: Mapped[float] = mapped_column(Float)
    value_hex: Mapped[str] = mapped_column(String(64))
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_records.id", ondelete="CASCADE"))
    derived_file_id: Mapped[str] = mapped_column(ForeignKey("derived_files.id", ondelete="CASCADE"))
    created_at: Mapped[datetime]
