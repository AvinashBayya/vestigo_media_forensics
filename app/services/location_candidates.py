"""Location candidates (M6): create, list, edit, and delete analyst-stated possible locations.

Every create, update, and delete is recorded as an append-only custody event (D21) in the same
transaction. Everything stored here is the analyst's own statement; Vestigo verifies nothing and
makes no location claim of its own. Coordinates are sensitive, so they never appear in logs - only
artifact and candidate ids do.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.models import Artifact, DerivedFile, EvidenceRecord, ExternalLead, LocationCandidate
from app.schemas.common import ErrorCode, ReviewState
from app.schemas.location_candidates import (
    LocationCandidateCreate,
    LocationCandidateInfo,
    LocationCandidateUpdate,
    SupportRef,
)
from app.services import custody
from app.services.errors import artifact_not_found

logger = get_logger("location_candidates")

CANDIDATE_RECORDED = "location_candidate_recorded"
CANDIDATE_UPDATED = "location_candidate_updated"
CANDIDATE_DELETED = "location_candidate_deleted"

_EDITABLE_FIELDS = (
    "description",
    "basis",
    "analyst_assessment",
    "latitude",
    "longitude",
    "notes",
    "supports",
    "review_state",
)

# Each support type names the table it refers to and the id prefix it must carry.
_SUPPORT_MODELS = {
    "evidence_record": (EvidenceRecord, ids.EVIDENCE),
    "derived_file": (DerivedFile, ids.DERIVED_FILE),
    "external_lead": (ExternalLead, ids.EXTERNAL_LEAD),
}


def _candidate_not_found(candidate_id: str) -> AppError:
    return AppError(404, ErrorCode.NOT_FOUND, "Location candidate not found.", {"candidate_id": candidate_id})


def _to_info(candidate: LocationCandidate) -> LocationCandidateInfo:
    return LocationCandidateInfo(
        candidate_id=candidate.id,
        artifact_id=candidate.artifact_id,
        description=candidate.description,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        basis=candidate.basis,
        notes=candidate.notes,
        analyst_assessment=candidate.analyst_assessment,
        supports=[SupportRef.model_validate(ref) for ref in candidate.supports or []],
        review_state=ReviewState(candidate.review_state),
        recorded_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def _get_artifact(session: Session, artifact_id: str) -> Artifact:
    artifact = session.get(Artifact, artifact_id) if ids.is_valid_id(artifact_id, ids.ARTIFACT) else None
    if artifact is None:
        raise artifact_not_found(artifact_id)
    return artifact


def _validate_supports(session: Session, artifact_id: str, supports: list[SupportRef]) -> None:
    """Every cited support must exist and belong to the same artifact (M6-6)."""
    for ref in supports:
        model, prefix = _SUPPORT_MODELS[ref.type]
        row = session.get(model, ref.id) if ids.is_valid_id(ref.id, prefix) else None
        if row is None or row.artifact_id != artifact_id:
            raise AppError(
                404,
                ErrorCode.NOT_FOUND,
                f"Supporting {ref.type.replace('_', ' ')} not found for this artifact.",
                {"type": ref.type, "id": ref.id},
            )


def create_candidate(
    services: AppServices, artifact_id: str, payload: LocationCandidateCreate
) -> LocationCandidateInfo:
    with services.db.writer() as session, session.begin():
        artifact = _get_artifact(session, artifact_id)
        _validate_supports(session, artifact.id, payload.supports)
        candidate = LocationCandidate(
            id=ids.new_id(ids.LOCATION_CANDIDATE),
            artifact_id=artifact.id,
            description=payload.description,
            latitude=payload.latitude,
            longitude=payload.longitude,
            basis=payload.basis,
            notes=payload.notes,
            analyst_assessment=payload.analyst_assessment,
            supports=[ref.model_dump() for ref in payload.supports],
            review_state=ReviewState.UNREVIEWED,
            created_at=utcnow(),
            updated_at=None,
        )
        session.add(candidate)
        custody.record_event(
            session,
            artifact.id,
            CANDIDATE_RECORDED,
            {
                "candidate_id": candidate.id,
                "analyst_assessment": candidate.analyst_assessment,
                # Coordinates are sensitive: the custody trail records only whether any were given.
                "has_coordinates": candidate.latitude is not None,
                "support_count": len(candidate.supports),
            },
        )
        info = _to_info(candidate)
    # Only the artifact id is logged: coordinates and notes are sensitive (05 §7).
    log_event(logger, logging.INFO, "location_candidate.recorded", artifact_id=artifact_id)
    return info


def list_candidates(session: Session, artifact_id: str) -> list[LocationCandidateInfo]:
    rows = session.scalars(
        select(LocationCandidate)
        .where(LocationCandidate.artifact_id == artifact_id)
        .order_by(LocationCandidate.created_at.desc(), LocationCandidate.id.desc())
    )
    return [_to_info(candidate) for candidate in rows]


def get_candidates(services: AppServices, artifact_id: str) -> list[LocationCandidateInfo]:
    with services.db.reader() as session:
        _get_artifact(session, artifact_id)
        return list_candidates(session, artifact_id)


def _get_candidate(session: Session, artifact_id: str, candidate_id: str) -> LocationCandidate:
    _get_artifact(session, artifact_id)
    candidate = (
        session.get(LocationCandidate, candidate_id)
        if ids.is_valid_id(candidate_id, ids.LOCATION_CANDIDATE)
        else None
    )
    if candidate is None or candidate.artifact_id != artifact_id:
        raise _candidate_not_found(candidate_id)
    return candidate


def update_candidate(
    services: AppServices, artifact_id: str, candidate_id: str, update: LocationCandidateUpdate
) -> LocationCandidateInfo:
    with services.db.writer() as session, session.begin():
        candidate = _get_candidate(session, artifact_id, candidate_id)
        given = update.model_dump(exclude_unset=True)
        if "supports" in given:
            _validate_supports(session, artifact_id, update.supports or [])
        changed = sorted(
            field
            for field in _EDITABLE_FIELDS
            if field in given and getattr(candidate, field) != given[field]
        )
        for field in changed:
            setattr(candidate, field, given[field])
        if changed:  # a no-op save is not a custody event
            candidate.updated_at = utcnow()
            custody.record_event(
                session,
                artifact_id,
                CANDIDATE_UPDATED,
                # Field names only: no coordinate or note content in the custody trail.
                {"candidate_id": candidate.id, "fields": changed},
            )
        info = _to_info(candidate)
    if changed:
        log_event(logger, logging.INFO, "location_candidate.updated", artifact_id=artifact_id)
    return info


def delete_candidate(services: AppServices, artifact_id: str, candidate_id: str) -> None:
    with services.db.writer() as session, session.begin():
        candidate = _get_candidate(session, artifact_id, candidate_id)
        custody.record_event(
            session,
            artifact_id,
            CANDIDATE_DELETED,
            {"candidate_id": candidate.id, "analyst_assessment": candidate.analyst_assessment},
        )
        session.delete(candidate)
    log_event(logger, logging.INFO, "location_candidate.deleted", artifact_id=artifact_id)
