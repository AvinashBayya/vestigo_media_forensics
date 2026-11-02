from datetime import datetime

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_artifacts_size_positive"),
        CheckConstraint("length(sha256) = 64", name="ck_artifacts_sha256_length"),
        CheckConstraint("length(md5) = 32", name="ck_artifacts_md5_length"),
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
