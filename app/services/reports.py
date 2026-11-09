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
    ForensicIndicatorsSection,
    HashesSection,
    KeyframeOCRSection,
    KeyframePHashSection,
    KeyframesSection,
    LocationCluesSection,
    MediaInfoSection,
    MetadataSection,
    OCRPreprocessingStep,
    OCRSection,
    PdfImagesSection,
    PdfStructureSection,
    PdfTextSection,
    PerceptualHashSection,
    Provenance,
    SceneChangesSection,
    StageError,
    StructuralSection,
)
from app.services import leads, location_candidates, review
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
        analyst_notes=record.analyst_notes,
        review_updated_at=record.review_updated_at,
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
        validation_performed=payload.get("validation_performed", False),
        manifest_labels=payload.get("manifest_labels", []),
        details=payload.get("details", {}),
        status=payload.get("status"),
        validation_state=payload.get("validation_state"),
        manifest_count=payload.get("manifest_count"),
        active_manifest=payload.get("active_manifest"),
        manifests=payload.get("manifests", []),
        validation_codes=payload.get("validation_codes"),
        validator=payload.get("validator"),
        validator_error=payload.get("validator_error"),
        provenance=provenance,
    )


def _location_clues(payload: dict[str, Any], provenance: Provenance) -> LocationCluesSection:
    return LocationCluesSection(
        coordinates=payload.get("coordinates", []),
        altitude_meters=payload.get("altitude_meters"),
        altitude_as_written=payload.get("altitude_as_written"),
        altitude_reference=payload.get("altitude_reference"),
        text_clues=payload.get("text_clues", []),
        timestamps=payload.get("timestamps", []),
        device=payload.get("device", []),
        iso6709=payload.get("iso6709", []),
        ocr_available=payload.get("ocr_available", False),
        provenance=provenance,
    )


def _structural(payload: dict[str, Any], provenance: Provenance) -> StructuralSection:
    return StructuralSection(
        container=payload.get("container"),
        file_size=payload.get("file_size", 0),
        logical_end=payload.get("logical_end"),
        trailing_bytes=payload.get("trailing_bytes", 0),
        findings=payload.get("findings", []),
        inventory=payload.get("inventory", []),
        measurements=payload.get("measurements", []),
        notes=payload.get("notes", []),
        warnings=payload.get("warnings", []),
        binwalk_ran=payload.get("binwalk_ran", False),
        provenance=provenance,
    )


def _forensic_indicators(payload: dict[str, Any], provenance: Provenance) -> ForensicIndicatorsSection:
    return ForensicIndicatorsSection(
        container=payload.get("container"),
        quantization_tables=payload.get("quantization_tables", []),
        channel_statistics=payload.get("channel_statistics", []),
        decoded_width=payload.get("decoded_width"),
        decoded_height=payload.get("decoded_height"),
        declared_width=payload.get("declared_width"),
        declared_height=payload.get("declared_height"),
        dimensions_match=payload.get("dimensions_match"),
        video_statistics=payload.get("video_statistics", {}),
        notes=payload.get("notes", []),
        warnings=payload.get("warnings", []),
        provenance=provenance,
    )


def _pdf_structure(payload: dict[str, Any], provenance: Provenance) -> PdfStructureSection:
    return PdfStructureSection(**{**payload, "provenance": provenance})


def _pdf_text(payload: dict[str, Any], provenance: Provenance) -> PdfTextSection:
    return PdfTextSection(**{**payload, "provenance": provenance})


def _pdf_images(payload: dict[str, Any], provenance: Provenance) -> PdfImagesSection:
    return PdfImagesSection(
        images=payload.get("images", []),
        extracted=payload.get("extracted", 0),
        notes=payload.get("notes", []),
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


def _media_info(payload: dict[str, Any], provenance: Provenance) -> MediaInfoSection:
    return MediaInfoSection(
        container=payload.get("container", {"stream_count": 0}),
        video_streams=payload.get("video_streams", []),
        audio_streams=payload.get("audio_streams", []),
        other_streams=payload.get("other_streams", []),
        provenance=provenance,
    )


def _scene_changes(payload: dict[str, Any], provenance: Provenance) -> SceneChangesSection:
    return SceneChangesSection(
        threshold=payload.get("threshold"),
        count=payload.get("count", 0),
        changes=payload.get("changes", []),
        provenance=provenance,
    )


def _keyframes(payload: dict[str, Any], provenance: Provenance) -> KeyframesSection:
    return KeyframesSection(
        policy=payload.get("policy", {}),
        requested=payload.get("requested", 0),
        extracted=payload.get("extracted", 0),
        frames=payload.get("frames", []),
        provenance=provenance,
    )


def _keyframe_phash(payload: dict[str, Any], provenance: Provenance) -> KeyframePHashSection:
    return KeyframePHashSection(
        bits=payload.get("bits", BITS),
        count=payload.get("count", 0),
        frames=payload.get("frames", []),
        provenance=provenance,
    )


def _keyframe_ocr(payload: dict[str, Any], provenance: Provenance) -> KeyframeOCRSection:
    return KeyframeOCRSection(
        languages=payload.get("languages", list(LANGUAGES)),
        frame_limit=payload.get("frame_limit", 0),
        analyzed=payload.get("analyzed", 0),
        frames=payload.get("frames", []),
        provenance=provenance,
    )


def _duplicates(
    matched: dict[str, tuple[str, str]],
) -> Callable[[dict[str, Any], Provenance], DuplicatesSection]:
    def build(payload: dict[str, Any], provenance: Provenance) -> DuplicatesSection:
        matches = [
            DuplicateMatch(
                artifact_id=match["artifact_id"],
                filename=matched[match["artifact_id"]][0] if match["artifact_id"] in matched else None,
                available=match["artifact_id"] in matched,
                media_type=matched[match["artifact_id"]][1] if match["artifact_id"] in matched else None,
                similarity=match["similarity"],
                distance=match["distance"],
                match_type=match["match_type"],
                matched_frame_count=match.get("matched_frame_count"),
                frame_matches=match.get("frame_matches"),
            )
            for match in payload.get("matches", [])
        ]
        return DuplicatesSection(
            threshold=payload.get("threshold"),
            library_size=payload.get("library_size"),
            compared=payload.get("compared"),
            excluded_count=payload.get("excluded_count"),
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
        review_history = review.history(session, artifact_id)
        external_leads = leads.list_leads(session, artifact_id)
        candidates = location_candidates.list_candidates(session, artifact_id)
        duplicates = records.get("duplicates")
        matches = duplicates.payload.get("matches", []) if duplicates else []
        matched_ids = {match["artifact_id"] for match in matches}
        matched = {
            row[0]: (row[1], row[2])
            for row in session.execute(
                select(Artifact.id, Artifact.original_filename, Artifact.media_type).where(
                    Artifact.id.in_(matched_ids)
                )
            ).all()
        }

    builders: dict[str, Callable[[dict[str, Any], Provenance], BaseModel]] = {
        "hashes": _hashes,
        "metadata": _metadata,
        "c2pa": _c2pa,
        "location_clues": _location_clues,
        "structural": _structural,
        "forensic_indicators": _forensic_indicators,
        "pdf_structure": _pdf_structure,
        "pdf_text": _pdf_text,
        "pdf_images": _pdf_images,
        "perceptual_hash": _perceptual_hash,
        "ocr": _ocr,
        "duplicates": _duplicates(matched),
        "media_info": _media_info,
        "scene_changes": _scene_changes,
        "keyframes": _keyframes,
        "keyframe_phash": _keyframe_phash,
        "keyframe_ocr": _keyframe_ocr,
    }
    sections = {
        stage: build(records[stage].payload, _provenance(records[stage], derived.get(stage, [])))
        if stage in records
        else None
        for stage, build in builders.items()
    }
    clues = sections.get("location_clues")
    if isinstance(clues, LocationCluesSection):
        # Point the analyst at this job's OCR text, if any, instead of interpreting it (M6-4).
        clues.ocr_available = any(
            stage in records
            and bool(records[stage].payload.get("text") or records[stage].payload.get("frames"))
            for stage in ("ocr", "keyframe_ocr")
        )
    return EvidenceReport(
        artifact_id=artifact.id,
        job_id=job.id,
        created_at=utcnow(),
        artifact=to_summary(artifact, latest.status if latest else None),
        job=to_job_summary(job),
        review=to_review_info(artifact),
        review_history=review_history,
        external_leads=external_leads,
        location_candidates=candidates,
        **sections,
    )
