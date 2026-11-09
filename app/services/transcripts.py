"""Machine transcripts (Pass 1, D24): local speech-to-text over an artifact's audio.

A transcript is machine-generated, potentially inaccurate, and unverified. It is derived material,
never evidence, and the original audio is only ever read - never replaced, trimmed, or rewritten.
For a video, the audio track is extracted with the ffmpeg Vestigo already uses and kept as a derived
file, so the transcript's source lineage is explicit rather than implied. The analyst's corrections
are stored beside the model's text, never over it.
"""

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.core.tools import ToolError, run_tool
from app.models import AnalysisJob, Artifact, DerivedFile, Transcript
from app.schemas.common import ErrorCode, JobStatus, MediaType, ReviewState
from app.schemas.transcripts import TranscriptInfo, TranscriptSegmentInfo, TranscriptUpdate
from app.services import ai, app_settings, custody
from app.services.errors import artifact_not_found

logger = get_logger("transcripts")

TRANSCRIPT_CREATED = "transcript_created"
TRANSCRIPT_EDITED = "transcript_edited"
TRANSCRIPT_DELETED = "transcript_deleted"

# 16 kHz mono PCM: what small ASR models expect, and a format ffmpeg can always produce.
AUDIO_ARGS = ("-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le")
EXTRACTED_AUDIO_KIND = "transcription_audio"


def _transcript_not_found(transcript_id: str) -> AppError:
    return AppError(404, ErrorCode.NOT_FOUND, "Transcript not found.", {"transcript_id": transcript_id})


def _get_artifact(session: Session, artifact_id: str) -> Artifact:
    artifact = session.get(Artifact, artifact_id) if ids.is_valid_id(artifact_id, ids.ARTIFACT) else None
    if artifact is None:
        raise artifact_not_found(artifact_id)
    return artifact


def _to_info(transcript: Transcript) -> TranscriptInfo:
    return TranscriptInfo(
        transcript_id=transcript.id,
        artifact_id=transcript.artifact_id,
        derived_file_id=transcript.derived_file_id,
        language=transcript.language,
        duration_seconds=transcript.duration_seconds,
        text=transcript.text,
        edited_text=transcript.edited_text,
        segments=[TranscriptSegmentInfo.model_validate(segment) for segment in transcript.segments or []],
        model=transcript.model or {},
        warnings=list(transcript.warnings or []),
        review_state=ReviewState(transcript.review_state),
        created_at=transcript.created_at,
        updated_at=transcript.updated_at,
    )


def _latest_job_id(session: Session, artifact_id: str) -> str | None:
    job = session.scalars(
        select(AnalysisJob)
        .where(AnalysisJob.artifact_id == artifact_id, AnalysisJob.status == JobStatus.COMPLETED)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
    ).first()
    return job.id if job is not None else None


def _prepare_audio(services: AppServices, artifact: Artifact) -> tuple[object, str | None, list[str]]:
    """The audio to transcribe. Videos get their track extracted; the original is only read."""
    storage = services.storage
    source = storage.resolve(artifact.stored_path)
    if artifact.media_type == MediaType.AUDIO:
        return source, None, []

    temp = storage.new_temp_path(".wav")
    tool = services.tools.require("ffmpeg")
    try:
        completed = run_tool(
            tool,
            ["-v", "error", "-y", "-i", source, *AUDIO_ARGS, temp],
            timeout=services.settings.video_timeout_seconds,
        )
        if completed.returncode != 0 or not temp.is_file() or temp.stat().st_size == 0:
            raise ToolError(f"ffmpeg exited with code {completed.returncode}.")
    except (ToolError, OSError) as exc:
        temp.unlink(missing_ok=True)
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "The audio track could not be extracted from this video. The original is unchanged.",
            {"artifact_id": artifact.id},
        ) from exc

    data = temp.read_bytes()
    with services.db.reader() as session:
        job_id = _latest_job_id(session, artifact.id)
    if job_id is None:
        # Nothing to attach a derived file to; transcribe the temporary copy and say it was not kept.
        return (
            temp,
            None,
            [
                "The extracted audio track was not retained as a derived file because this artifact has "
                "no completed analysis to attach it to. Run an analysis first for full lineage."
            ],
        )

    directory = storage.derived_dir(artifact.id, job_id)
    directory.mkdir(parents=True, exist_ok=True)
    stored = directory / "transcription.audio.wav"
    stored.write_bytes(data)
    temp.unlink(missing_ok=True)
    derived_id = ids.new_id(ids.DERIVED_FILE)
    with services.db.writer() as session, session.begin():
        session.add(
            DerivedFile(
                id=derived_id,
                artifact_id=artifact.id,
                job_id=job_id,
                stage="transcription",
                kind=EXTRACTED_AUDIO_KIND,
                stored_path=storage.relative(stored),
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
                created_at=utcnow(),
                # Lineage (M4B): extracted from the original, which is never modified.
                source_kind="original",
                source_derived_file_id=None,
            )
        )
    return stored, derived_id, []


def create_transcript(services: AppServices, artifact_id: str, language: str | None = None) -> TranscriptInfo:
    editable = app_settings.get_settings_response(services).editable
    transcriber = ai.resolve_transcriber(
        enabled=editable.transcription_enabled, model_path=editable.transcription_model_path
    )

    with services.db.reader() as session:
        artifact = _get_artifact(session, artifact_id)
    if artifact.media_type == MediaType.IMAGE:
        raise AppError(
            422,
            ErrorCode.WRONG_MEDIA_TYPE,
            "Only audio and video artifacts have audio to transcribe.",
            {"artifact_id": artifact_id, "media_type": artifact.media_type},
        )

    # Refuse before extracting anything. `_prepare_audio` runs ffmpeg and commits a derived file, so
    # asking first keeps a turned-off feature from leaving derived evidence and custody behind.
    unavailable = ai.unavailable_reason(transcriber)
    if unavailable is not None:
        raise AppError(409, ErrorCode.AI_UNAVAILABLE, unavailable, {"artifact_id": artifact_id})

    audio_path, derived_id, warnings = _prepare_audio(services, artifact)
    try:
        result = transcriber.transcribe(audio_path, language)
    except ai.AIUnavailableError as exc:
        raise AppError(409, ErrorCode.AI_UNAVAILABLE, exc.reason, {"artifact_id": artifact_id}) from exc

    now = utcnow()
    with services.db.writer() as session, session.begin():
        transcript = Transcript(
            id=ids.new_id(ids.TRANSCRIPT),
            artifact_id=artifact_id,
            derived_file_id=derived_id,
            language=result.language,
            duration_seconds=result.duration_seconds or artifact.duration_seconds,
            text=result.text,
            segments=[
                {
                    "start": segment.start_seconds,
                    "end": segment.end_seconds,
                    "text": segment.text,
                    "words": segment.words,
                }
                for segment in result.segments
            ],
            edited_text=None,
            model=result.model.as_dict(),
            warnings=[*warnings, *result.warnings],
            review_state=ReviewState.UNREVIEWED,
            created_at=now,
            updated_at=None,
        )
        session.add(transcript)
        custody.record_event(
            session,
            artifact_id,
            TRANSCRIPT_CREATED,
            {
                "transcript_id": transcript.id,
                "model": result.model.name,
                "language": result.language,
                "segments": len(transcript.segments),
                # No transcript text in the custody trail.
                "derived_file_id": derived_id,
            },
        )
        info = _to_info(transcript)
    log_event(logger, logging.INFO, "transcript.created", artifact_id=artifact_id)
    return info


def list_transcripts(session: Session, artifact_id: str) -> list[TranscriptInfo]:
    rows = session.scalars(
        select(Transcript)
        .where(Transcript.artifact_id == artifact_id)
        .order_by(Transcript.created_at.desc(), Transcript.id.desc())
    )
    return [_to_info(transcript) for transcript in rows]


def get_transcripts(services: AppServices, artifact_id: str) -> list[TranscriptInfo]:
    with services.db.reader() as session:
        _get_artifact(session, artifact_id)
        return list_transcripts(session, artifact_id)


def _get_transcript(session: Session, artifact_id: str, transcript_id: str) -> Transcript:
    _get_artifact(session, artifact_id)
    transcript = (
        session.get(Transcript, transcript_id) if ids.is_valid_id(transcript_id, ids.TRANSCRIPT) else None
    )
    if transcript is None or transcript.artifact_id != artifact_id:
        raise _transcript_not_found(transcript_id)
    return transcript


def update_transcript(
    services: AppServices, artifact_id: str, transcript_id: str, update: TranscriptUpdate
) -> TranscriptInfo:
    """Store the analyst's correction beside the model's text, and their review state."""
    with services.db.writer() as session, session.begin():
        transcript = _get_transcript(session, artifact_id, transcript_id)
        given = update.model_dump(exclude_unset=True)
        changed = sorted(
            field
            for field in ("edited_text", "review_state")
            if field in given and getattr(transcript, field) != given[field]
        )
        for field in changed:
            setattr(transcript, field, given[field])
        if changed:
            transcript.updated_at = utcnow()
            custody.record_event(
                session,
                artifact_id,
                TRANSCRIPT_EDITED,
                {"transcript_id": transcript.id, "fields": changed},
            )
        info = _to_info(transcript)
    if changed:
        log_event(logger, logging.INFO, "transcript.edited", artifact_id=artifact_id)
    return info


def delete_transcript(services: AppServices, artifact_id: str, transcript_id: str) -> None:
    """Delete the transcript. The extracted audio stays as a derived file of its analysis."""
    with services.db.writer() as session, session.begin():
        transcript = _get_transcript(session, artifact_id, transcript_id)
        custody.record_event(
            session,
            artifact_id,
            TRANSCRIPT_DELETED,
            {"transcript_id": transcript.id, "model": (transcript.model or {}).get("name")},
        )
        session.delete(transcript)
    log_event(logger, logging.INFO, "transcript.deleted", artifact_id=artifact_id)
