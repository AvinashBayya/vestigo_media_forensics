"""Assembles the evidence report for one analysis job from its evidence records."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.database import Database
from app.core.errors import AppError
from app.models import AnalysisJob, Artifact, DerivedFile, EvidenceRecord
from app.schemas.common import ACTIVE_JOB_STATUSES, ErrorCode
from app.schemas.evidence import (
    C2PASection,
    DerivedFileInfo,
    DuplicateMatch,
    DuplicatesSection,
    EvidenceReport,
    HashesSection,
    MetadataSection,
    OCRPreprocessingStep,
    OCRSection,
    PerceptualHashSection,
    Provenance,
    StageError,
)
from app.services.analysis import active_job, latest_job, to_job_summary
from app.services.artifacts import get_artifact, to_review_info, to_summary
from app.services.errors import analysis_in_progress, job_not_found
from app.services.metadata import SECTIONS
from app.services.ocr import LANGUAGES
from app.services.phash import BITS


def _provenance(record: EvidenceRecord, derived: list[DerivedFile]) -> Provenance:
    return Provenance(
        evidence_id=record.id,
        stage=record.stage,
        status=record.status,
        classification=record.classification,
        method=record.method,
        source=record.source,
        tool=record.tool,
        tool_version=record.tool_version,
        started_at=record.started_at,
        completed_at=record.completed_at,
        limitations=record.limitations,
        errors=[StageError(**error) for error in record.errors],
        review_state=record.review_state,
        skip_reason=record.payload.get("skip_reason") if record.status == "skipped" else None,
        derived_files=[
            DerivedFileInfo(derived_file_id=f.id, kind=f.kind, sha256=f.sha256, size_bytes=f.size_bytes)
            for f in derived
        ],
    )


def _hashes(payload: dict[str, Any], provenance: Provenance) -> HashesSection:
    return HashesSection(
        sha256=payload.get("sha256"),
        md5=payload.get("md5"),
        matches_upload_record=payload.get("matches_upload_record"),
        provenance=provenance,
    )


def _metadata(payload: dict[str, Any], provenance: Provenance) -> MetadataSection:
    return MetadataSection(**{name: payload.get(name, {}) for name in SECTIONS}, provenance=provenance)


def _c2pa(payload: dict[str, Any], provenance: Provenance) -> C2PASection:
    return C2PASection(
        present=payload.get("present"),
        manifest_labels=payload.get("manifest_labels", []),
        details=payload.get("details", {}),
        provenance=provenance,
    )


def _perceptual_hash(payload: dict[str, Any], provenance: Provenance) -> PerceptualHashSection:
    return PerceptualHashSection(
        bits=payload.get("bits", BITS), value=payload.get("value"), provenance=provenance
    )


def _ocr_steps(raw: list[Any]) -> list[OCRPreprocessingStep]:
    # Records made before two-pass OCR stored preprocessing as plain sentences.
    return [
        OCRPreprocessingStep(step="note", applied=True, description=item)
        if isinstance(item, str)
        else OCRPreprocessingStep.model_validate(item)
        for item in raw
    ]


def _ocr(payload: dict[str, Any], provenance: Provenance) -> OCRSection:
    return OCRSection(
        languages=payload.get("languages", list(LANGUAGES)),
        text=payload.get("text", ""),
        cleaned_text=payload.get("cleaned_text"),
        cleaning=payload.get("cleaning", []),
        confidence=payload.get("confidence"),
        word_count=payload.get("word_count", 0),
        preprocessing=_ocr_steps(payload.get("preprocessing", [])),
        candidates=payload.get("candidates", []),
        selected=payload.get("selected"),
        provenance=provenance,
    )


def _duplicates(filenames: dict[str, str]) -> Callable[[dict[str, Any], Provenance], DuplicatesSection]:
    def build(payload: dict[str, Any], provenance: Provenance) -> DuplicatesSection:
        matches = [
            DuplicateMatch(
                artifact_id=match["artifact_id"],
                filename=filenames.get(match["artifact_id"]),
                available=match["artifact_id"] in filenames,
                similarity=match["similarity"],
                distance=match["distance"],
                match_type=match["match_type"],
            )
            for match in payload.get("matches", [])
        ]
        return DuplicatesSection(
            threshold=payload.get("threshold"),
            library_size=payload.get("library_size"),
            compared=payload.get("compared"),
            matches=matches,
            provenance=provenance,
        )

    return build


def _select_job(session: Session, artifact_id: str, job_id: str | None) -> AnalysisJob:
    if job_id is not None:
        job = session.get(AnalysisJob, job_id) if ids.is_valid_id(job_id, ids.JOB) else None
        if job is None or job.artifact_id != artifact_id:
            raise job_not_found(job_id)
        if job.status in ACTIVE_JOB_STATUSES:
            raise analysis_in_progress(job)
        return job
    stmt = (
        select(AnalysisJob)
        .where(AnalysisJob.artifact_id == artifact_id, AnalysisJob.status.not_in(ACTIVE_JOB_STATUSES))
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .limit(1)
    )
    job = session.scalar(stmt)
    if job is None:
        running = active_job(session, artifact_id)
        raise AppError(
            404,
            ErrorCode.EVIDENCE_NOT_FOUND,
            "This artifact has no finished analysis yet.",
            {"artifact_id": artifact_id, "active_job_id": running.id if running else None},
        )
    return job


def build_report(db: Database, artifact_id: str, job_id: str | None = None) -> EvidenceReport:
    artifact = get_artifact(db, artifact_id)
    with db.reader() as session:
        job = _select_job(session, artifact_id, job_id)
        records = {
            record.stage: record
            for record in session.scalars(select(EvidenceRecord).where(EvidenceRecord.job_id == job.id))
        }
        derived: dict[str, list[DerivedFile]] = {}
        for file in session.scalars(select(DerivedFile).where(DerivedFile.job_id == job.id)):
            derived.setdefault(file.stage, []).append(file)
        latest = latest_job(session, artifact_id)
        duplicates = records.get("duplicates")
        matches = duplicates.payload.get("matches", []) if duplicates else []
        matched_ids = {match["artifact_id"] for match in matches}
        filenames = dict(
            session.execute(
                select(Artifact.id, Artifact.original_filename).where(Artifact.id.in_(matched_ids))
            ).all()
        )

    builders: dict[str, Callable[[dict[str, Any], Provenance], BaseModel]] = {
        "hashes": _hashes,
        "metadata": _metadata,
        "c2pa": _c2pa,
        "perceptual_hash": _perceptual_hash,
        "ocr": _ocr,
        "duplicates": _duplicates(filenames),
    }
    sections = {
        stage: build(records[stage].payload, _provenance(records[stage], derived.get(stage, [])))
        if stage in records
        else None
        for stage, build in builders.items()
    }
    return EvidenceReport(
        artifact_id=artifact.id,
        job_id=job.id,
        created_at=utcnow(),
        artifact=to_summary(artifact, latest.status if latest else None),
        job=to_job_summary(job),
        review=to_review_info(artifact),
        **sections,
    )
