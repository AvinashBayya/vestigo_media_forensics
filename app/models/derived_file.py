from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DerivedFile(Base):
    """A file produced during analysis, such as raw tool output. Stored apart from the original."""

    __tablename__ = "derived_files"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    stored_path: Mapped[str] = mapped_column(String(255), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    created_at: Mapped[datetime]
    # What this file was made from (M4B): "original" or "derived_file". NULL on rows written
    # before revision 0005 — reported as "source not recorded", never guessed.
    source_kind: Mapped[str | None] = mapped_column(String(16))
    source_derived_file_id: Mapped[str | None] = mapped_column(ForeignKey("derived_files.id"))
