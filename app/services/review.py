"""Review workflow: artifact review, bulk review, per-record review, and history (M2-2, M2-3, M2-5).

Every change to a review state or note writes an append-only review event with the full note text
before and after. Saving without a change writes nothing. Review never touches evidence
classification, payloads, or anything produced by analysis.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.database import Database
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.models import Artifact, EvidenceRecord, ReviewEvent
from app.schemas.artifact import ReviewUpdate
from app.schemas.common import ErrorCode, ReviewState
from app.schemas.review import (
    BulkReviewRequest,
    BulkReviewResult,
    RecordReview,
    RecordReviewUpdate,
    ReviewEventOut,
    ReviewHistory,
)
from app.services.errors import artifact_not_found

logger = get_logger("review")


def review_conflict(current: dict[str, object]) -> AppError:
    return AppError(
        409,
        ErrorCode.REVIEW_CONFLICT,
        "This review was changed elsewhere since you opened it. Reload to see the current review, then "
        "make your change again.",
        {"current": current},
    )


def evidence_record_not_found(evidence_id: str) -> AppError:
    return AppError(
        404, ErrorCode.EVIDENCE_RECORD_NOT_FOUND, "Evidence record not found.", {"evidence_id": evidence_id}
    )


def _event(
    artifact_id: str,
    origin: str,
    from_state: str,
    to_state: str,
    notes_before: str,
    notes_after: str,
    at: datetime,
    evidence_id: str | None = None,
) -> ReviewEvent:
    return ReviewEvent(
        id=ids.new_id(ids.REVIEW_EVENT),
        artifact_id=artifact_id,
        evidence_id=evidence_id,
        origin=origin,
        from_state=from_state,
        to_state=to_state,
        notes_before=notes_before,
        notes_after=notes_after,
        created_at=at,
    )


def _locked_artifact(session: Session, artifact_id: str) -> Artifact:
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise artifact_not_found(artifact_id)
    return artifact


def update_artifact_review(db: Database, artifact_id: str, update: ReviewUpdate) -> None:
    with db.writer() as session, session.begin():
        artifact = _locked_artifact(session, artifact_id)
        if (
            "expected_updated_at" in update.model_fields_set
            and update.expected_updated_at != artifact.review_updated_at
        ):
            raise review_conflict(
                {
                    "state": artifact.review_state,
                    "analyst_notes": artifact.analyst_notes,
                    "updated_at": artifact.review_updated_at.isoformat(),
                }
            )
        if update.state == artifact.review_state and update.analyst_notes == artifact.analyst_notes:
            return
        now = utcnow()
        session.add(
            _event(
                artifact.id,
                "artifact",
                artifact.review_state,
                update.state,
                artifact.analyst_notes,
                update.analyst_notes,
                now,
            )
        )
        artifact.review_state = update.state
        artifact.analyst_notes = update.analyst_notes
        artifact.review_updated_at = now
    log_event(logger, logging.INFO, "artifact.review_updated", artifact_id=artifact_id, status=update.state)


def bulk_review(db: Database, request: BulkReviewRequest) -> BulkReviewResult:
    """Set one review state on many artifacts, all or nothing. Notes are not changed."""
    requested = list(dict.fromkeys(request.artifact_ids))
    with db.writer() as session, session.begin():
        found = {
            artifact.id: artifact
            for artifact in session.scalars(select(Artifact).where(Artifact.id.in_(requested)))
        }
        # Malformed IDs are never found, so they are reported as missing too.
        missing = sorted(artifact_id for artifact_id in requested if artifact_id not in found)
        if missing:
            raise AppError(
                404,
                ErrorCode.ARTIFACT_NOT_FOUND,
                f"{len(missing)} of the selected artifacts no longer exist. Nothing was changed.",
                {"missing": missing},
            )
        now = utcnow()
        updated, unchanged = [], []
        for artifact_id in requested:
            artifact = found[artifact_id]
            if artifact.review_state == request.state:
                unchanged.append(artifact_id)
                continue
            session.add(
                _event(
                    artifact_id,
                    "bulk",
                    artifact.review_state,
                    request.state,
                    artifact.analyst_notes,
                    artifact.analyst_notes,
                    now,
                )
            )
            artifact.review_state = request.state
            artifact.review_updated_at = now
            updated.append(artifact_id)
    log_event(logger, logging.INFO, "artifact.bulk_review", status=request.state, count=len(updated))
    return BulkReviewResult(state=request.state, updated=updated, unchanged=unchanged)


def _to_record_review(record: EvidenceRecord) -> RecordReview:
    return RecordReview(
        evidence_id=record.id,
        artifact_id=record.artifact_id,
        job_id=record.job_id,
        stage=record.stage,
        classification=record.classification,
        review_state=ReviewState(record.review_state),
        analyst_notes=record.analyst_notes,
        review_updated_at=record.review_updated_at,
    )


def update_record_review(
    db: Database, artifact_id: str, evidence_id: str, update: RecordReviewUpdate
) -> RecordReview:
    with db.writer() as session, session.begin():
        _locked_artifact(session, artifact_id)
        record = (
            session.get(EvidenceRecord, evidence_id) if ids.is_valid_id(evidence_id, ids.EVIDENCE) else None
        )
        if record is None or record.artifact_id != artifact_id:
            raise evidence_record_not_found(evidence_id)
        if (
            "expected_updated_at" in update.model_fields_set
            and update.expected_updated_at != record.review_updated_at
        ):
            raise review_conflict(
                {
                    "state": record.review_state,
                    "analyst_notes": record.analyst_notes,
                    "updated_at": record.review_updated_at.isoformat() if record.review_updated_at else None,
                }
            )
        if update.state != record.review_state or update.analyst_notes != record.analyst_notes:
            now = utcnow()
            session.add(
                _event(
                    artifact_id,
                    "record",
                    record.review_state,
                    update.state,
                    record.analyst_notes,
                    update.analyst_notes,
                    now,
                    evidence_id=record.id,
                )
            )
            record.review_state = update.state
            record.analyst_notes = update.analyst_notes
            record.review_updated_at = now
        result = _to_record_review(record)
    log_event(logger, logging.INFO, "evidence.review_updated", artifact_id=artifact_id, status=update.state)
    return result


def history(session: Session, artifact_id: str) -> list[ReviewEventOut]:
    rows = session.execute(
        select(ReviewEvent, EvidenceRecord.stage, EvidenceRecord.job_id)
        .outerjoin(EvidenceRecord, EvidenceRecord.id == ReviewEvent.evidence_id)
        .where(ReviewEvent.artifact_id == artifact_id)
        .order_by(ReviewEvent.created_at.desc(), ReviewEvent.id.desc())
    ).all()
    return [
        ReviewEventOut(
            event_id=event.id,
            origin=event.origin,
            evidence_id=event.evidence_id,
            stage=stage,
            job_id=job_id,
            from_state=ReviewState(event.from_state),
            to_state=ReviewState(event.to_state),
            notes_before=event.notes_before,
            notes_after=event.notes_after,
            created_at=event.created_at,
        )
        for event, stage, job_id in rows
    ]


def get_history(db: Database, artifact_id: str) -> ReviewHistory:
    with db.reader() as session:
        _locked_artifact(session, artifact_id)
        return ReviewHistory(artifact_id=artifact_id, events=history(session, artifact_id))
