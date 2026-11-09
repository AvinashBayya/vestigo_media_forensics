from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Case(Base):
    """An analyst's case: a name and notes that group artifacts (Pass 3, D26).

    A case is organisation, not evidence: it carries no classification and asserts nothing about
    the artifacts in it. Deleting a case never deletes an artifact.
    """

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]


class CaseArtifact(Base):
    """One artifact's membership of one case. Deleting either side removes only the link."""

    __tablename__ = "case_artifacts"
    __table_args__ = (Index("ix_case_artifacts_artifact", "artifact_id"),)

    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"), primary_key=True)
    added_at: Mapped[datetime]
