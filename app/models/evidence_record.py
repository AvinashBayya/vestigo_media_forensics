from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EvidenceRecord(Base):
    """One pipeline stage's result for one job (04-EVIDENCE-MODEL.md)."""

    __tablename__ = "evidence_records"
    __table_args__ = (
        UniqueConstraint("job_id", "stage", name="uq_evidence_records_job_stage"),
        CheckConstraint("json_array_length(limitations_json) > 0", name="ck_evidence_records_limitations"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    classification: Mapped[str] = mapped_column(String(16))
    method: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(128))
    tool: Mapped[str] = mapped_column(String(128))
    # NULL only when the tool was never invoked (stage skipped or tool unavailable).
    tool_version: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column("payload_json", JSON)
    errors: Mapped[list[dict[str, Any]]] = mapped_column("errors_json", JSON)
    limitations: Mapped[list[str]] = mapped_column("limitations_json", JSON)
    review_state: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime]
