"""Artifact lifecycle: upload, lookup, listing, and review state."""

import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select

from app.core import ids
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.database import Database
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.core.storage import Storage
from app.models import AnalysisJob, Artifact
from app.schemas.artifact import ArtifactDetail, ArtifactSummary, ReviewInfo, ReviewUpdate
from app.schemas.common import ErrorCode, JobStatus, MediaType, ReviewState
from app.services import analysis
from app.services.errors import artifact_not_found
from app.services.hashing import CHUNK_SIZE, FileHasher, FileHashes
from app.services.validation import (
    SNIFF_BYTES,
    ImageTooLargeError,
    InvalidImageError,
    inspect_image,
    sniff_image_format,
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


def create_artifact(services: AppServices, stream: BinaryIO, filename: str | None) -> Artifact:
    settings, storage = services.settings, services.storage
    received = receive_upload(stream, storage, settings.max_upload_bytes)
    artifact_id = ids.new_id(ids.ARTIFACT)
    try:
        image_format = sniff_image_format(received.head)
        if image_format is None:
            raise AppError(
                415,
                ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                "Only JPEG, PNG, WebP, and TIFF images are supported in Milestone 1.",
            )
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
        stored_path = storage.store_original(received.temp_path, artifact_id, image_format.extension)
    except BaseException:
        received.temp_path.unlink(missing_ok=True)
        raise

    now = utcnow()
    artifact = Artifact(
        id=artifact_id,
        original_filename=sanitize_filename(filename),
        media_type=MediaType.IMAGE,
        mime_type=image_format.mime_type,
        size_bytes=received.hashes.size_bytes,
        sha256=received.hashes.sha256,
        md5=received.hashes.md5,
        width=info.width,
        height=info.height,
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


def to_summary(artifact: Artifact, latest_job_status: str | None) -> ArtifactSummary:
    return ArtifactSummary(
        artifact_id=artifact.id,
        filename=artifact.original_filename,
        media_type=MediaType(artifact.media_type),
        mime_type=artifact.mime_type,
        size_bytes=artifact.size_bytes,
        created_at=artifact.created_at,
        review_state=ReviewState(artifact.review_state),
        latest_job_status=JobStatus(latest_job_status) if latest_job_status else None,
    )


def get_artifact_detail(db: Database, artifact_id: str) -> ArtifactDetail:
    artifact = get_artifact(db, artifact_id)
    with db.reader() as session:
        job = analysis.latest_job(session, artifact_id)
    summary = to_summary(artifact, job.status if job else None)
    return ArtifactDetail(
        **summary.model_dump(),
        sha256=artifact.sha256,
        md5=artifact.md5,
        width=artifact.width,
        height=artifact.height,
        review=to_review_info(artifact),
        latest_job=analysis.to_job_summary(job) if job else None,
    )


def to_review_info(artifact: Artifact) -> ReviewInfo:
    return ReviewInfo(
        state=ReviewState(artifact.review_state),
        analyst_notes=artifact.analyst_notes,
        updated_at=artifact.review_updated_at,
    )


def list_artifacts(db: Database, limit: int, offset: int) -> tuple[list[ArtifactSummary], int]:
    latest_status = (
        select(AnalysisJob.status)
        .where(AnalysisJob.artifact_id == Artifact.id)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .limit(1)
        .correlate(Artifact)
        .scalar_subquery()
    )
    stmt = (
        select(Artifact, latest_status)
        .order_by(Artifact.created_at.desc(), Artifact.id.desc())
        .limit(limit)
        .offset(offset)
    )
    with db.reader() as session:
        total = session.scalar(select(func.count()).select_from(Artifact)) or 0
        rows = session.execute(stmt).all()
    return [to_summary(artifact, status) for artifact, status in rows], total


def update_review(db: Database, artifact_id: str, update: ReviewUpdate) -> None:
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)
    with db.writer() as session, session.begin():
        artifact = session.get(Artifact, artifact_id)
        if artifact is None:
            raise artifact_not_found(artifact_id)
        artifact.review_state = update.state
        artifact.analyst_notes = update.analyst_notes
        artifact.review_updated_at = utcnow()
    log_event(logger, logging.INFO, "artifact.review_updated", artifact_id=artifact_id, status=update.state)
