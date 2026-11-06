from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.analysis_job import AnalysisJob
from app.models.app_setting import AppSetting
from app.models.artifact import Artifact
from app.models.base import Base
from app.models.custody_event import CustodyEvent
from app.models.derived_file import DerivedFile
from app.models.evidence_record import EvidenceRecord
from app.models.external_lead import ExternalLead
from app.models.fingerprint import ImageFingerprint
from app.models.keyframe_fingerprint import KeyframeFingerprint
from app.models.playable_preview import PlayablePreview
from app.models.review_event import ReviewEvent


class SchemaMeta(Base):
    __tablename__ = "schema_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


__all__ = [
    "AnalysisJob",
    "AppSetting",
    "Artifact",
    "Base",
    "CustodyEvent",
    "DerivedFile",
    "EvidenceRecord",
    "ExternalLead",
    "ImageFingerprint",
    "KeyframeFingerprint",
    "PlayablePreview",
    "ReviewEvent",
    "SchemaMeta",
]
