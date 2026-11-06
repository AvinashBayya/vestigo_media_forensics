"""Custody events (M4B): record state-changing actions that leave no trace in other tables.

The chain of custody is what Vestigo recorded on this machine since upload — never an invented or
legal chain of custody. Upload, analysis jobs, evidence records, and review changes live in their
own tables; only exports, duplicate-library changes, and preview creation are recorded here. The
table is append-only (database triggers from revision 0005).
"""

from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.database import Database
from app.models import AnalysisJob, Artifact, CustodyEvent, DerivedFile, EvidenceRecord, ReviewEvent
from app.schemas.custody import CustodyDerivedFile, CustodyReport, CustodyTimelineEvent
from app.services.errors import artifact_not_found

EXPORTED = "exported"
LIBRARY_CHANGED = "library_changed"
PREVIEW_CREATED = "preview_created"


def record_event(session: Session, artifact_id: str, event_type: str, detail: dict[str, Any]) -> CustodyEvent:
    event = CustodyEvent(
        id=ids.new_id(ids.CUSTODY_EVENT),
        artifact_id=artifact_id,
        event_type=event_type,
        detail=detail,
        created_at=utcnow(),
    )
    session.add(event)
    return event


def _count_by_job(session: Session, model: type, artifact_id: str) -> dict[str, int]:
    rows = session.execute(
        select(model.job_id, func.count()).where(model.artifact_id == artifact_id).group_by(model.job_id)
    ).all()
    return dict(rows)


def build_custody_report(db: Database, artifact_id: str) -> CustodyReport:
    """Merge every recorded fact about the artifact into one chronological timeline (M4B).

    Sources are the existing tables plus custody_events; nothing is duplicated or inferred.
    Granularity: one entry per analysis job (started/finished), not per pipeline stage - the
    per-stage detail stays in the evidence report.
    """
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)
    with db.reader() as session:
        artifact = session.get(Artifact, artifact_id)
        if artifact is None:
            raise artifact_not_found(artifact_id)

        events = [
            CustodyTimelineEvent(
                type="uploaded",
                at=artifact.created_at,
                source_table="artifacts",
                detail={
                    "filename": artifact.original_filename,
                    "media_type": artifact.media_type,
                    "mime_type": artifact.mime_type,
                    "size_bytes": artifact.size_bytes,
                    "sha256": artifact.sha256,
                },
            )
        ]

        record_counts = _count_by_job(session, EvidenceRecord, artifact_id)
        file_counts = _count_by_job(session, DerivedFile, artifact_id)
        jobs = session.scalars(
            select(AnalysisJob)
            .where(AnalysisJob.artifact_id == artifact_id)
            .order_by(AnalysisJob.created_at, AnalysisJob.id)
        )
        for job in jobs:
            base = {"job_id": job.id, "pipeline": job.pipeline, "app_version": job.app_version}
            events.append(
                CustodyTimelineEvent(
                    type="analysis_started",
                    at=job.started_at or job.created_at,
                    source_table="analysis_jobs",
                    detail=base,
                )
            )
            if job.completed_at is not None:
                detail = {
                    **base,
                    "status": job.status,
                    "evidence_records": record_counts.get(job.id, 0),
                    "derived_files": file_counts.get(job.id, 0),
                }
                if job.error_code is not None:
                    detail["error_code"] = job.error_code
                events.append(
                    CustodyTimelineEvent(
                        type="analysis_finished",
                        at=job.completed_at,
                        source_table="analysis_jobs",
                        detail=detail,
                    )
                )

        review_rows = session.execute(
            select(ReviewEvent, EvidenceRecord.stage)
            .outerjoin(EvidenceRecord, EvidenceRecord.id == ReviewEvent.evidence_id)
            .where(ReviewEvent.artifact_id == artifact_id)
            .order_by(ReviewEvent.created_at, ReviewEvent.id)
        ).all()
        for event, stage in review_rows:
            events.append(
                CustodyTimelineEvent(
                    type="review_changed",
                    at=event.created_at,
                    source_table="review_events",
                    detail={
                        "origin": event.origin,
                        "evidence_id": event.evidence_id,
                        "stage": stage,
                        "from_state": event.from_state,
                        "to_state": event.to_state,
                        # The full note text stays in the review history; here only the fact.
                        "notes_changed": event.notes_before != event.notes_after,
                    },
                )
            )

        for custody_event in session.scalars(
            select(CustodyEvent)
            .where(CustodyEvent.artifact_id == artifact_id)
            .order_by(CustodyEvent.created_at, CustodyEvent.id)
        ):
            events.append(
                CustodyTimelineEvent(
                    type=custody_event.event_type,
                    at=custody_event.created_at,
                    source_table="custody_events",
                    detail=custody_event.detail,
                )
            )

        derived = [
            CustodyDerivedFile(
                derived_file_id=row.id,
                job_id=row.job_id,
                stage=row.stage,
                kind=row.kind,
                filename=Path(row.stored_path).name,
                sha256=row.sha256,
                size_bytes=row.size_bytes,
                created_at=row.created_at,
                source_kind=row.source_kind,
                source_derived_file_id=row.source_derived_file_id,
            )
            for row in session.scalars(
                select(DerivedFile)
                .where(DerivedFile.artifact_id == artifact_id)
                .order_by(DerivedFile.created_at, DerivedFile.stored_path)
            )
        ]

    events.sort(key=lambda event: event.at)
    return CustodyReport(artifact_id=artifact_id, events=events, derived_files=derived)
