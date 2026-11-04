"""Artifact lifecycle: upload, lookup, listing, and review state."""

import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.database import Database
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.core.storage import Storage
from app.models import AnalysisJob, Artifact, DerivedFile, EvidenceRecord, PlayablePreview, ReviewEvent
from app.schemas.artifact import ArtifactDetail, ArtifactSummary, DeletionSummary, ReviewInfo
from app.schemas.common import ErrorCode, JobStatus, MediaType, ReviewState
from app.services import analysis, library
from app.services.errors import analysis_in_progress, artifact_not_found
from app.services.hashing import CHUNK_SIZE, FileHasher, FileHashes
from app.services.validation import (
    AUDIO_CAPABLE_FAMILIES,
    SNIFF_BYTES,
    AudioTooLongError,
    ImageTooLargeError,
    InvalidAudioError,
    InvalidImageError,
    InvalidVideoError,
    VideoResolutionError,
    VideoTooLongError,
    has_real_video_stream,
    inspect_audio,
    inspect_image,
    inspect_video,
    probe_video,
    sniff_image_format,
    sniff_video_container,
)

logger = get_logger("artifacts")

MAX_FILENAME_LENGTH = 255


@dataclass(frozen=True)
class ReceivedUpload:
    temp_path: Path
    hashes: FileHashes
    head: bytes


def sanitize_filename(name: str | None) -> str:
    """Reduce a client-supplied filename to a safe display name. It is never used as a path."""
    if not name:
        return "upload"
    name = unicodedata.normalize("NFC", name).replace("\\", "/").rsplit("/", 1)[-1]
    # Drop control and formatting characters, including right-to-left overrides used to disguise
    # extensions.
    name = "".join(ch for ch in name if not unicodedata.category(ch).startswith("C")).strip()
    if name in ("", ".", ".."):
        return "upload"
    return name[:MAX_FILENAME_LENGTH]


def receive_upload(stream: BinaryIO, storage: Storage, max_bytes: int) -> ReceivedUpload:
    """Copy an upload into tmp/ in chunks, hashing as it goes and stopping at the size limit."""
    temp_path = storage.new_temp_path(".part")
    hasher = FileHasher()
    head = b""
    try:
        with temp_path.open("xb") as out:
            while chunk := stream.read(CHUNK_SIZE):
                if hasher.size_bytes + len(chunk) > max_bytes:
                    raise AppError(
                        413,
                        ErrorCode.FILE_TOO_LARGE,
                        f"File exceeds the maximum upload size of {max_bytes // (1024 * 1024)} MB.",
                        {"max_bytes": max_bytes},
                    )
                if len(head) < SNIFF_BYTES:
                    head += chunk[: SNIFF_BYTES - len(head)]
                hasher.update(chunk)
                out.write(chunk)
        if hasher.size_bytes == 0:
            raise AppError(400, ErrorCode.EMPTY_FILE, "The uploaded file is empty.")
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return ReceivedUpload(temp_path, hasher.result(), head)


@dataclass(frozen=True)
class ValidatedMedia:
    """What upload validation established from the file's own bytes."""

    media_type: MediaType
    mime_type: str
    extension: str
    width: int | None
    height: int | None
    # Container-reported for videos (decision M3-8); None for images.
    duration_seconds: float | None


def _file_too_large(max_bytes: int) -> AppError:
    return AppError(
        413,
        ErrorCode.FILE_TOO_LARGE,
        f"File exceeds the maximum upload size of {max_bytes // (1024 * 1024)} MB.",
        {"max_bytes": max_bytes},
    )


def _validate_image(services: AppServices, received: ReceivedUpload, image_format: object) -> ValidatedMedia:
    settings = services.settings
    if received.hashes.size_bytes > settings.max_upload_bytes:
        raise _file_too_large(settings.max_upload_bytes)
    try:
        info = inspect_image(received.temp_path, image_format, settings.max_image_pixels)
    except ImageTooLargeError as exc:
        raise AppError(
            422,
            ErrorCode.IMAGE_TOO_LARGE,
            f"Image exceeds the maximum of {settings.max_image_pixels:,} pixels.",
            {"max_pixels": settings.max_image_pixels},
        ) from exc
    except InvalidImageError as exc:
        raise AppError(
            422,
            ErrorCode.INVALID_IMAGE,
            f"The file starts like a {image_format.name.upper()} image but could not be read as one.",
        ) from exc
    return ValidatedMedia(
        MediaType.IMAGE, image_format.mime_type, image_format.extension, info.width, info.height, None
    )


def _validate_av(services: AppServices, received: ReceivedUpload, container: str) -> ValidatedMedia:
    """One ffprobe run decides whether an AV container is a video or an audio artifact (D19)."""
    settings = services.settings
    try:
        probe = probe_video(
            services.tools.require("ffprobe"), received.temp_path, settings.tool_timeout_seconds
        )
    except InvalidVideoError as exc:
        raise AppError(
            422,
            ErrorCode.INVALID_VIDEO,
            f"The file starts like a media container but could not be validated: {exc}.",
        ) from exc
    if has_real_video_stream(probe.data.get("streams", [])):
        return _validate_video(services, received, container, probe.data)
    if container in AUDIO_CAPABLE_FAMILIES:
        return _validate_audio(services, received, container, probe.data)
    raise AppError(
        422,
        ErrorCode.INVALID_VIDEO,
        "The file starts like a video container but could not be validated: the file contains no "
        "video stream.",
    )


def _validate_video(
    services: AppServices, received: ReceivedUpload, container: str, probe: dict
) -> ValidatedMedia:
    settings = services.settings
    if received.hashes.size_bytes > settings.max_video_upload_bytes:
        raise _file_too_large(settings.max_video_upload_bytes)
    try:
        info = inspect_video(
            probe,
            container,
            received.head,
            max_pixels=settings.max_video_pixels,
            max_duration_seconds=settings.max_video_duration_seconds,
        )
    except VideoTooLongError as exc:
        raise AppError(
            422,
            ErrorCode.VIDEO_TOO_LONG,
            f"Video duration {exc.duration_seconds:g} s exceeds the maximum of "
            f"{settings.max_video_duration_seconds:g} s.",
            {"max_duration_seconds": settings.max_video_duration_seconds},
        ) from exc
    except VideoResolutionError as exc:
        raise AppError(
            422,
            ErrorCode.VIDEO_RESOLUTION_TOO_LARGE,
            f"Video frames of {exc.width}x{exc.height} exceed the maximum of "
            f"{settings.max_video_pixels:,} pixels.",
            {"max_pixels": settings.max_video_pixels},
        ) from exc
    except InvalidVideoError as exc:
        raise AppError(
            422,
            ErrorCode.INVALID_VIDEO,
            f"The file starts like a video container but could not be validated: {exc}.",
        ) from exc
    return ValidatedMedia(
        MediaType.VIDEO,
        info.format.mime_type,
        info.format.extension,
        info.width,
        info.height,
        info.duration_seconds,
    )


def _validate_audio(
    services: AppServices, received: ReceivedUpload, container: str, probe: dict
) -> ValidatedMedia:
    settings = services.settings
    if received.hashes.size_bytes > settings.max_audio_upload_bytes:
        raise _file_too_large(settings.max_audio_upload_bytes)
    try:
        info = inspect_audio(probe, container, max_duration_seconds=settings.max_audio_duration_seconds)
    except AudioTooLongError as exc:
        raise AppError(
            422,
            ErrorCode.AUDIO_TOO_LONG,
            f"Audio duration {exc.duration_seconds:g} s exceeds the maximum of "
            f"{settings.max_audio_duration_seconds:g} s.",
            {"max_duration_seconds": settings.max_audio_duration_seconds},
        ) from exc
    except InvalidAudioError as exc:
        raise AppError(
            422,
            ErrorCode.INVALID_AUDIO,
            f"The file starts like an audio container but could not be validated: {exc}.",
        ) from exc
    return ValidatedMedia(
        MediaType.AUDIO, info.format.mime_type, info.format.extension, None, None, info.duration_seconds
    )


def create_artifact(services: AppServices, stream: BinaryIO, filename: str | None) -> Artifact:
    settings, storage = services.settings, services.storage
    stream_cap = max(settings.max_upload_bytes, settings.max_video_upload_bytes)
    received = receive_upload(stream, storage, stream_cap)
    artifact_id = ids.new_id(ids.ARTIFACT)
    try:
        image_format = sniff_image_format(received.head)
        video_container = sniff_video_container(received.head) if image_format is None else None
        if image_format is not None:
            media = _validate_image(services, received, image_format)
        elif video_container is not None:
            media = _validate_av(services, received, video_container)
        else:
            raise AppError(
                415,
                ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                "Only JPEG, PNG, WebP, and TIFF images, MP4, MOV, WebM, MKV, AVI, MPEG-TS, WMV, "
                "FLV, and 3GP videos, and WAV, MP3, FLAC, OGG, and M4A audio files are supported.",
            )
        stored_path = storage.store_original(received.temp_path, artifact_id, media.extension)
    except BaseException:
        received.temp_path.unlink(missing_ok=True)
        raise

    now = utcnow()
    artifact = Artifact(
        id=artifact_id,
        original_filename=sanitize_filename(filename),
        media_type=media.media_type,
        mime_type=media.mime_type,
        size_bytes=received.hashes.size_bytes,
        sha256=received.hashes.sha256,
        md5=received.hashes.md5,
        width=media.width,
        height=media.height,
        duration_seconds=media.duration_seconds,
        stored_path=stored_path,
        review_state=ReviewState.UNREVIEWED,
        analyst_notes="",
        review_updated_at=now,
        created_at=now,
    )
    try:
        with services.db.writer() as session, session.begin():
            session.add(artifact)
    except BaseException:
        storage.purge(storage.artifact_dir(artifact_id))
        raise
    log_event(logger, logging.INFO, "artifact.uploaded", artifact_id=artifact_id)
    return artifact


def get_artifact(db: Database, artifact_id: str) -> Artifact:
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)
    with db.reader() as session:
        artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise artifact_not_found(artifact_id)
    return artifact


def get_derived_file(db: Database, artifact_id: str, derived_file_id: str) -> DerivedFile:
    """The derived file, only if it belongs to this artifact."""
    artifact = get_artifact(db, artifact_id)
    derived = None
    if ids.is_valid_id(derived_file_id, ids.DERIVED_FILE):
        with db.reader() as session:
            derived = session.get(DerivedFile, derived_file_id)
    if derived is None or derived.artifact_id != artifact.id:
        raise AppError(
            404, ErrorCode.NOT_FOUND, "Derived file not found.", {"derived_file_id": derived_file_id}
        )
    return derived


def to_summary(artifact: Artifact, latest_job_status: str | None) -> ArtifactSummary:
    return ArtifactSummary(
        artifact_id=artifact.id,
        filename=artifact.original_filename,
        media_type=MediaType(artifact.media_type),
        mime_type=artifact.mime_type,
        size_bytes=artifact.size_bytes,
        created_at=artifact.created_at,
        duration_seconds=artifact.duration_seconds,
        review_state=ReviewState(artifact.review_state),
        latest_job_status=JobStatus(latest_job_status) if latest_job_status else None,
    )


def get_artifact_detail(db: Database, artifact_id: str) -> ArtifactDetail:
    artifact = get_artifact(db, artifact_id)
    with db.reader() as session:
        item = library.list_item(session, artifact_id)
        has_preview = session.get(PlayablePreview, artifact_id) is not None
    if item is None:
        raise artifact_not_found(artifact_id)
    return ArtifactDetail(
        **item.model_dump(),
        sha256=artifact.sha256,
        md5=artifact.md5,
        width=artifact.width,
        height=artifact.height,
        has_playable_preview=has_preview,
        review=to_review_info(artifact),
    )


def set_duplicate_library(db: Database, artifact_id: str, included: bool) -> None:
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)
    with db.writer() as session, session.begin():
        artifact = session.get(Artifact, artifact_id)
        if artifact is None:
            raise artifact_not_found(artifact_id)
        library.set_duplicate_library(session, artifact, included)
    log_event(
        logger,
        logging.INFO,
        "artifact.duplicate_library_updated",
        artifact_id=artifact_id,
        status="included" if included else "excluded",
    )


def to_review_info(artifact: Artifact) -> ReviewInfo:
    return ReviewInfo(
        state=ReviewState(artifact.review_state),
        analyst_notes=artifact.analyst_notes,
        updated_at=artifact.review_updated_at,
    )


def _count(session: Session, model: type, artifact_id: str) -> int:
    return (
        session.scalar(select(func.count()).select_from(model).where(model.artifact_id == artifact_id)) or 0
    )


def _delete_rows(session: Session, artifact_id: str) -> None:
    # Jobs, evidence records, derived-file rows, fingerprints, and review events cascade from the
    # artifact row.
    session.execute(delete(Artifact).where(Artifact.id == artifact_id))


def delete_artifact(services: AppServices, artifact_id: str) -> DeletionSummary:
    """Delete the original, derived files, jobs, evidence records, and database rows (D11).

    The artifact folder is moved to trash/ first and moved back if the database deletion fails, so
    files and rows are never left out of step.
    """
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)
    storage = services.storage
    trashed = None
    try:
        with services.db.writer() as session, session.begin():
            if session.get(Artifact, artifact_id) is None:
                raise artifact_not_found(artifact_id)
            running = analysis.active_job(session, artifact_id)
            if running is not None:
                raise analysis_in_progress(running)
            original_files, derived_files = storage.count_files(artifact_id)
            summary = DeletionSummary(
                artifact_id=artifact_id,
                original_files=original_files,
                derived_files=derived_files,
                jobs=_count(session, AnalysisJob, artifact_id),
                evidence_records=_count(session, EvidenceRecord, artifact_id),
                review_events=_count(session, ReviewEvent, artifact_id),
                preview_files=1 if session.get(PlayablePreview, artifact_id) is not None else 0,
            )
            trashed = storage.move_to_trash(artifact_id)
            _delete_rows(session, artifact_id)
    except BaseException:
        if trashed is not None:
            storage.restore_from_trash(trashed, artifact_id)
        raise

    if trashed is not None:
        try:
            storage.purge(trashed)
        except OSError as exc:
            # The rows are gone; leftover files in trash/ are removed at the next startup.
            log_event(
                logger,
                logging.WARNING,
                "artifact.purge_failed",
                artifact_id=artifact_id,
                error_type=type(exc).__name__,
            )
    log_event(logger, logging.INFO, "artifact.deleted", artifact_id=artifact_id)
    return summary
