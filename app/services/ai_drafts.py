"""AI drafts (Pass 1, D24): fields a local model proposed, for the analyst to accept, edit, or reject.

A draft is never evidence. It is produced from material Vestigo already holds, stored outside the
evidence tables, labelled "AI-generated, unverified - analyst must review", and never written back
over metadata, evidence, or any analyst record. Generation and each per-field decision are recorded
as append-only custody events; no draft content ever enters custody details or the logs.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.models import AIDraft, Artifact, EvidenceRecord, Transcript
from app.schemas.ai_drafts import AIDraftInfo, DraftField, DraftGenerateRequest, FieldDecision
from app.schemas.common import ErrorCode
from app.services import ai, app_settings, custody
from app.services.errors import artifact_not_found

logger = get_logger("ai_drafts")

DRAFT_GENERATED = "ai_draft_generated"
DRAFT_FIELD_REVIEWED = "ai_draft_field_reviewed"
DRAFT_DELETED = "ai_draft_deleted"

# How much held text one draft may read, so a huge OCR dump cannot stall a local model.
MAX_SOURCE_CHARACTERS = 20_000


def _draft_not_found(draft_id: str) -> AppError:
    return AppError(404, ErrorCode.NOT_FOUND, "AI draft not found.", {"draft_id": draft_id})


def _get_artifact(session: Session, artifact_id: str) -> Artifact:
    artifact = session.get(Artifact, artifact_id) if ids.is_valid_id(artifact_id, ids.ARTIFACT) else None
    if artifact is None:
        raise artifact_not_found(artifact_id)
    return artifact


def _latest_record(session: Session, artifact_id: str, stage: str) -> EvidenceRecord | None:
    return session.scalars(
        select(EvidenceRecord)
        .where(EvidenceRecord.artifact_id == artifact_id, EvidenceRecord.stage == stage)
        .order_by(EvidenceRecord.completed_at.desc(), EvidenceRecord.id.desc())
    ).first()


def _metadata_lines(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for section, groups in payload.items():
        if not isinstance(groups, dict):
            continue
        for group, tags in groups.items():
            if not isinstance(tags, dict):
                continue
            for tag, value in tags.items():
                if isinstance(value, dict | list):
                    continue
                lines.append(f"{section}:{group}:{tag} = {value}")
    return lines


def source_text(session: Session, artifact: Artifact, source_kind: str) -> tuple[str, str | None]:
    """The held text a draft may read, with the evidence record it came from when there is one."""
    if source_kind == "analyst_notes":
        return artifact.analyst_notes or "", None
    if source_kind == "ocr_text":
        record = _latest_record(session, artifact.id, "ocr")
        if record is not None:
            payload = record.payload or {}
            return str(payload.get("cleaned_text") or payload.get("text") or ""), record.id
        frames_record = _latest_record(session, artifact.id, "keyframe_ocr")
        if frames_record is not None:
            frames = (frames_record.payload or {}).get("frames") or []
            text = "\n".join(
                str(frame.get("cleaned_text") or frame.get("text") or "")
                for frame in frames
                if isinstance(frame, dict)
            )
            return text.strip(), frames_record.id
        return "", None
    if source_kind == "metadata":
        record = _latest_record(session, artifact.id, "metadata")
        if record is None:
            return "", None
        return "\n".join(_metadata_lines(record.payload or {})), record.id
    if source_kind == "transcript":
        transcript = session.scalars(
            select(Transcript)
            .where(Transcript.artifact_id == artifact.id)
            .order_by(Transcript.created_at.desc(), Transcript.id.desc())
        ).first()
        if transcript is None:
            return "", None
        return (transcript.edited_text or transcript.text or ""), None
    raise AppError(
        422, ErrorCode.VALIDATION_ERROR, f"Unknown draft source: {source_kind}.", {"source": source_kind}
    )


def _to_info(draft: AIDraft) -> AIDraftInfo:
    return AIDraftInfo(
        draft_id=draft.id,
        artifact_id=draft.artifact_id,
        kind=draft.kind,
        source_kind=draft.source_kind,
        source_evidence_id=draft.source_evidence_id,
        fields=[DraftField.model_validate(field) for field in draft.fields or []],
        status=draft.status,
        model=draft.model or {},
        reasoning=draft.reasoning,
        warnings=list(draft.warnings or []),
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


def generate_draft(services: AppServices, artifact_id: str, request: DraftGenerateRequest) -> AIDraftInfo:
    """Ask the local model for the requested fields, and store the result as a draft."""
    editable = app_settings.get_settings_response(services).editable
    extractor = ai.resolve_extractor(enabled=editable.ai_enabled, model_path=editable.ai_model_path)

    with services.db.reader() as session:
        artifact = _get_artifact(session, artifact_id)
        text, evidence_id = source_text(session, artifact, request.source_kind)

    if not text.strip():
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            f"There is no {request.source_kind.replace('_', ' ')} to read for this artifact yet.",
            {"artifact_id": artifact_id, "source": request.source_kind},
        )
    try:
        result = extractor.extract(text[:MAX_SOURCE_CHARACTERS], list(request.fields))
    except ai.AIUnavailableError as exc:
        # Unavailable is a plain, actionable 409: the feature is off or the runtime is absent.
        raise AppError(409, ErrorCode.AI_UNAVAILABLE, exc.reason, {"artifact_id": artifact_id}) from exc

    now = utcnow()
    with services.db.writer() as session, session.begin():
        draft = AIDraft(
            id=ids.new_id(ids.AI_DRAFT),
            artifact_id=artifact_id,
            kind="field_extraction",
            source_kind=request.source_kind,
            source_evidence_id=evidence_id,
            fields=[
                {
                    "name": field.name,
                    "value": field.value,
                    # Recorded only when the model supplied one; Vestigo never invents a confidence.
                    "confidence": field.confidence,
                    "status": "proposed",
                    "edited_value": None,
                }
                for field in result.fields
            ],
            status="proposed",
            model=result.model.as_dict(),
            reasoning=result.reasoning,
            warnings=list(result.warnings),
            created_at=now,
            updated_at=None,
        )
        session.add(draft)
        custody.record_event(
            session,
            artifact_id,
            DRAFT_GENERATED,
            {
                "draft_id": draft.id,
                "source_kind": draft.source_kind,
                # Field names and the model only: no extracted content in the custody trail.
                "field_names": [field["name"] for field in draft.fields],
                "model": result.model.name,
            },
        )
        info = _to_info(draft)
    log_event(logger, logging.INFO, "ai_draft.generated", artifact_id=artifact_id)
    return info


def list_drafts(session: Session, artifact_id: str) -> list[AIDraftInfo]:
    rows = session.scalars(
        select(AIDraft)
        .where(AIDraft.artifact_id == artifact_id)
        .order_by(AIDraft.created_at.desc(), AIDraft.id.desc())
    )
    return [_to_info(draft) for draft in rows]


def get_drafts(services: AppServices, artifact_id: str) -> list[AIDraftInfo]:
    with services.db.reader() as session:
        _get_artifact(session, artifact_id)
        return list_drafts(session, artifact_id)


def _get_draft(session: Session, artifact_id: str, draft_id: str) -> AIDraft:
    _get_artifact(session, artifact_id)
    draft = session.get(AIDraft, draft_id) if ids.is_valid_id(draft_id, ids.AI_DRAFT) else None
    if draft is None or draft.artifact_id != artifact_id:
        raise _draft_not_found(draft_id)
    return draft


def decide_field(
    services: AppServices, artifact_id: str, draft_id: str, decision: FieldDecision
) -> AIDraftInfo:
    """Accept, edit, or reject one proposed field. The model's own value is always kept."""
    with services.db.writer() as session, session.begin():
        draft = _get_draft(session, artifact_id, draft_id)
        fields = [dict(field) for field in draft.fields or []]
        target = next((field for field in fields if field.get("name") == decision.field), None)
        if target is None:
            raise AppError(
                404,
                ErrorCode.NOT_FOUND,
                "That field is not part of this draft.",
                {"draft_id": draft_id, "field": decision.field},
            )
        target["status"] = decision.action
        # An edit stores the analyst's text beside the model's, never over it.
        target["edited_value"] = decision.value if decision.action == "edited" else None
        draft.fields = fields
        draft.status = (
            "proposed" if any(field.get("status") == "proposed" for field in fields) else "reviewed"
        )
        draft.updated_at = utcnow()
        custody.record_event(
            session,
            artifact_id,
            DRAFT_FIELD_REVIEWED,
            {"draft_id": draft.id, "field": decision.field, "action": decision.action},
        )
        info = _to_info(draft)
    log_event(logger, logging.INFO, "ai_draft.field_reviewed", artifact_id=artifact_id)
    return info


def delete_draft(services: AppServices, artifact_id: str, draft_id: str) -> None:
    with services.db.writer() as session, session.begin():
        draft = _get_draft(session, artifact_id, draft_id)
        custody.record_event(
            session, artifact_id, DRAFT_DELETED, {"draft_id": draft.id, "source_kind": draft.source_kind}
        )
        session.delete(draft)
    log_event(logger, logging.INFO, "ai_draft.deleted", artifact_id=artifact_id)
