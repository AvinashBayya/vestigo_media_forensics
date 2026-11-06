"""External leads (M5): create, list, edit, and delete analyst-recorded search results.

Every create, update, and delete is recorded as an append-only custody event (D21) in the same
transaction. Vestigo never contacts a provider: everything here is what the analyst typed in.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.models import Artifact, DerivedFile, ExternalLead
from app.schemas.common import ErrorCode, MediaType, ReviewState
from app.schemas.leads import ExternalLeadCreate, ExternalLeadInfo, ExternalLeadUpdate
from app.services import custody
from app.services.errors import artifact_not_found

logger = get_logger("leads")

LEAD_RECORDED = "lead_recorded"
LEAD_UPDATED = "lead_updated"
LEAD_DELETED = "lead_deleted"

# The fields an update may change; review_state is included - lead review is lightweight (M5).
_EDITABLE_FIELDS = ("provider", "result_url", "image_url", "claimed_published_at", "notes", "review_state")


def _lead_not_found(lead_id: str) -> AppError:
    return AppError(404, ErrorCode.NOT_FOUND, "External lead not found.", {"lead_id": lead_id})


def _to_info(lead: ExternalLead) -> ExternalLeadInfo:
    return ExternalLeadInfo(
        lead_id=lead.id,
        artifact_id=lead.artifact_id,
        derived_file_id=lead.derived_file_id,
        provider=lead.provider,
        result_url=lead.result_url,
        image_url=lead.image_url,
        claimed_published_at=lead.claimed_published_at,
        notes=lead.notes,
        review_state=ReviewState(lead.review_state),
        recorded_at=lead.created_at,
        updated_at=lead.updated_at,
    )


def _get_artifact(session: Session, artifact_id: str) -> Artifact:
    artifact = session.get(Artifact, artifact_id) if ids.is_valid_id(artifact_id, ids.ARTIFACT) else None
    if artifact is None:
        raise artifact_not_found(artifact_id)
    return artifact


def _validate_subject(session: Session, artifact: Artifact, derived_file_id: str | None) -> None:
    """The search subject must be the original image, or a real keyframe of this video (M5-2)."""
    if artifact.media_type == MediaType.AUDIO:
        raise AppError(
            422,
            ErrorCode.WRONG_MEDIA_TYPE,
            "External leads are recorded for image and video artifacts; audio has no searchable image.",
            {"artifact_id": artifact.id, "media_type": artifact.media_type},
        )
    if derived_file_id is None:
        if artifact.media_type == MediaType.VIDEO:
            raise AppError(
                422,
                ErrorCode.VALIDATION_ERROR,
                "For a video, the lead must name the searched keyframe (derived_file_id).",
                {"artifact_id": artifact.id},
            )
        return
    if artifact.media_type == MediaType.IMAGE:
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "For an image, the search subject is the original; omit derived_file_id.",
            {"artifact_id": artifact.id},
        )
    derived = (
        session.get(DerivedFile, derived_file_id)
        if ids.is_valid_id(derived_file_id, ids.DERIVED_FILE)
        else None
    )
    if derived is None or derived.artifact_id != artifact.id:
        raise AppError(
            404, ErrorCode.NOT_FOUND, "Derived file not found.", {"derived_file_id": derived_file_id}
        )
    if derived.kind != "keyframe_jpeg":
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "The search subject must be a keyframe; this derived file is not one.",
            {"derived_file_id": derived_file_id, "kind": derived.kind},
        )


def create_lead(services: AppServices, artifact_id: str, payload: ExternalLeadCreate) -> ExternalLeadInfo:
    with services.db.writer() as session, session.begin():
        artifact = _get_artifact(session, artifact_id)
        _validate_subject(session, artifact, payload.derived_file_id)
        lead = ExternalLead(
            id=ids.new_id(ids.EXTERNAL_LEAD),
            artifact_id=artifact.id,
            derived_file_id=payload.derived_file_id,
            provider=payload.provider,
            result_url=payload.result_url,
            image_url=payload.image_url,
            claimed_published_at=payload.claimed_published_at,
            notes=payload.notes,
            review_state=ReviewState.UNREVIEWED,
            created_at=utcnow(),
            updated_at=None,
        )
        session.add(lead)
        custody.record_event(
            session,
            artifact.id,
            LEAD_RECORDED,
            {"lead_id": lead.id, "provider": lead.provider, "derived_file_id": lead.derived_file_id},
        )
        info = _to_info(lead)
    log_event(logger, logging.INFO, "lead.recorded", artifact_id=artifact_id, lead_id=info.lead_id)
    return info


def list_leads(session: Session, artifact_id: str) -> list[ExternalLeadInfo]:
    rows = session.scalars(
        select(ExternalLead)
        .where(ExternalLead.artifact_id == artifact_id)
        .order_by(ExternalLead.created_at.desc(), ExternalLead.id.desc())
    )
    return [_to_info(lead) for lead in rows]


def get_leads(services: AppServices, artifact_id: str) -> list[ExternalLeadInfo]:
    with services.db.reader() as session:
        _get_artifact(session, artifact_id)
        return list_leads(session, artifact_id)


def _get_lead(session: Session, artifact_id: str, lead_id: str) -> ExternalLead:
    _get_artifact(session, artifact_id)
    lead = session.get(ExternalLead, lead_id) if ids.is_valid_id(lead_id, ids.EXTERNAL_LEAD) else None
    if lead is None or lead.artifact_id != artifact_id:
        raise _lead_not_found(lead_id)
    return lead


def update_lead(
    services: AppServices, artifact_id: str, lead_id: str, update: ExternalLeadUpdate
) -> ExternalLeadInfo:
    with services.db.writer() as session, session.begin():
        lead = _get_lead(session, artifact_id, lead_id)
        given = update.model_dump(exclude_unset=True)
        changed = sorted(
            field for field in _EDITABLE_FIELDS if field in given and getattr(lead, field) != given[field]
        )
        for field in changed:
            setattr(lead, field, given[field])
        if changed:  # a no-op save is not a custody event
            lead.updated_at = utcnow()
            custody.record_event(session, artifact_id, LEAD_UPDATED, {"lead_id": lead.id, "fields": changed})
        info = _to_info(lead)
    if changed:
        log_event(logger, logging.INFO, "lead.updated", artifact_id=artifact_id, lead_id=lead_id)
    return info


def delete_lead(services: AppServices, artifact_id: str, lead_id: str) -> None:
    with services.db.writer() as session, session.begin():
        lead = _get_lead(session, artifact_id, lead_id)
        custody.record_event(
            session, artifact_id, LEAD_DELETED, {"lead_id": lead.id, "provider": lead.provider}
        )
        session.delete(lead)
    log_event(logger, logging.INFO, "lead.deleted", artifact_id=artifact_id, lead_id=lead_id)
