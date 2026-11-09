"""Cases (Pass 3, D26): grouping artifacts, with every link in the artifact's custody trail.

A case is organisation. It never changes, re-classifies, or asserts anything about an artifact's
evidence, and deleting a case removes only the case and its links.
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.models import Artifact, Case, CaseArtifact
from app.schemas.cases import CaseArtifactRef, CaseCreate, CaseInfo, CaseUpdate
from app.schemas.common import ErrorCode
from app.services import custody
from app.services.errors import artifact_not_found

logger = get_logger("cases")

ARTIFACT_LINKED = "case_linked"
ARTIFACT_UNLINKED = "case_unlinked"


def _case_not_found(case_id: str) -> AppError:
    return AppError(404, ErrorCode.NOT_FOUND, "Case not found.", {"case_id": case_id})


def _get_case(session: Session, case_id: str) -> Case:
    case = session.get(Case, case_id) if ids.is_valid_id(case_id, ids.CASE) else None
    if case is None:
        raise _case_not_found(case_id)
    return case


def _to_info(session: Session, case: Case) -> CaseInfo:
    rows = session.execute(
        select(CaseArtifact, Artifact.original_filename, Artifact.media_type)
        .join(Artifact, Artifact.id == CaseArtifact.artifact_id)
        .where(CaseArtifact.case_id == case.id)
        .order_by(CaseArtifact.added_at, CaseArtifact.artifact_id)
    ).all()
    artifacts = [
        CaseArtifactRef(
            artifact_id=link.artifact_id,
            filename=filename,
            media_type=media_type,
            added_at=link.added_at,
        )
        for link, filename, media_type in rows
    ]
    return CaseInfo(
        case_id=case.id,
        name=case.name,
        notes=case.notes,
        artifact_count=len(artifacts),
        artifacts=artifacts,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def create_case(services: AppServices, payload: CaseCreate) -> CaseInfo:
    with services.db.writer() as session, session.begin():
        case = Case(
            id=ids.new_id(ids.CASE),
            name=payload.name,
            notes=payload.notes,
            created_at=utcnow(),
            updated_at=None,
        )
        session.add(case)
        session.flush()
        info = _to_info(session, case)
    log_event(logger, logging.INFO, "case.created")
    return info


def list_cases(services: AppServices) -> list[CaseInfo]:
    with services.db.reader() as session:
        cases = session.scalars(select(Case).order_by(Case.created_at.desc(), Case.id.desc()))
        return [_to_info(session, case) for case in cases]


def get_case(services: AppServices, case_id: str) -> CaseInfo:
    with services.db.reader() as session:
        return _to_info(session, _get_case(session, case_id))


def update_case(services: AppServices, case_id: str, update: CaseUpdate) -> CaseInfo:
    with services.db.writer() as session, session.begin():
        case = _get_case(session, case_id)
        given = update.model_dump(exclude_unset=True)
        nulled = sorted(name for name, value in given.items() if value is None)
        if nulled:
            raise AppError(
                422,
                ErrorCode.VALIDATION_ERROR,
                f"{', '.join(nulled)} cannot be null; omit the field to leave it unchanged.",
                {"case_id": case_id},
            )
        changed = [name for name, value in given.items() if getattr(case, name) != value]
        for name in changed:
            setattr(case, name, given[name])
        if changed:
            case.updated_at = utcnow()
        info = _to_info(session, case)
    return info


def delete_case(services: AppServices, case_id: str) -> None:
    """Delete the case and its links. No artifact and no evidence is touched."""
    with services.db.writer() as session, session.begin():
        case = _get_case(session, case_id)
        session.execute(delete(CaseArtifact).where(CaseArtifact.case_id == case.id))
        session.delete(case)
    log_event(logger, logging.INFO, "case.deleted")


def link_artifact(services: AppServices, case_id: str, artifact_id: str) -> CaseInfo:
    with services.db.writer() as session, session.begin():
        case = _get_case(session, case_id)
        if not ids.is_valid_id(artifact_id, ids.ARTIFACT) or session.get(Artifact, artifact_id) is None:
            raise artifact_not_found(artifact_id)
        existing = session.get(CaseArtifact, {"case_id": case.id, "artifact_id": artifact_id})
        if existing is None:
            session.add(CaseArtifact(case_id=case.id, artifact_id=artifact_id, added_at=utcnow()))
            # The artifact's own trail records which case it was put in.
            custody.record_event(
                session, artifact_id, ARTIFACT_LINKED, {"case_id": case.id, "case_name": case.name}
            )
        session.flush()
        info = _to_info(session, case)
    return info


def unlink_artifact(services: AppServices, case_id: str, artifact_id: str) -> CaseInfo:
    with services.db.writer() as session, session.begin():
        case = _get_case(session, case_id)
        existing = session.get(CaseArtifact, {"case_id": case.id, "artifact_id": artifact_id})
        if existing is not None:
            session.delete(existing)
            custody.record_event(
                session, artifact_id, ARTIFACT_UNLINKED, {"case_id": case.id, "case_name": case.name}
            )
        session.flush()
        info = _to_info(session, case)
    return info


def cases_for_artifact(session: Session, artifact_id: str) -> list[dict[str, str]]:
    """The cases an artifact belongs to, for its evidence report and the integration view."""
    rows = session.execute(
        select(Case.id, Case.name)
        .join(CaseArtifact, CaseArtifact.case_id == Case.id)
        .where(CaseArtifact.artifact_id == artifact_id)
        .order_by(Case.created_at)
    ).all()
    return [{"case_id": case_id, "name": name} for case_id, name in rows]
