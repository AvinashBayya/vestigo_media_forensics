from datetime import datetime

from sqlalchemy import CheckConstraint, Float, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_artifacts_size_positive"),
        CheckConstraint("length(sha256) = 64", name="ck_artifacts_sha256_length"),
        CheckConstraint("length(md5) = 32", name="ck_artifacts_md5_length"),
        Index("ix_artifacts_review_state", "review_state"),
        Index("ix_artifacts_size_bytes", "size_bytes"),
        Index("ix_artifacts_original_filename_nocase", text("original_filename COLLATE NOCASE")),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    # Sanitized, for display only. Never used to build a filesystem path.
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(16))
    mime_type: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    md5: Mapped[str] = mapped_column(String(32))
    width: Mapped[int | None]
    height: Mapped[int | None]
    # Relative to the data directory.
    stored_path: Mapped[str] = mapped_column(String(255), unique=True)
    review_state: Mapped[str] = mapped_column(String(16))
    analyst_notes: Mapped[str] = mapped_column(Text)
    review_updated_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(index=True)
    # False excludes the artifact from future duplicate searches (decision M2-7). Existing evidence is
    # never rewritten.
    in_duplicate_library: Mapped[bool] = mapped_column(default=True, server_default=text("1"))
    # Container-reported duration for videos (decision M3-8), as ffprobe read it at upload. Not a
    # decode-verified measurement. NULL for images.
    duration_seconds: Mapped[float | None] = mapped_column(Float)
