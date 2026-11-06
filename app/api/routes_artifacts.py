from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from app.api.deps import Services
from app.core.errors import AppError
from app.schemas.analysis import JobHistory
from app.schemas.artifact import (
    ArtifactDetail,
    ArtifactList,
    ArtifactQuery,
    ArtifactUploadResponse,
    DeletionSummary,
    PreviewInfo,
    ReviewUpdate,
)
from app.schemas.common import ErrorCode, MediaType
from app.schemas.custody import CustodyReport
from app.schemas.evidence import EvidenceReport
from app.schemas.library import DuplicateLibraryUpdate
from app.schemas.review import (
    BulkReviewRequest,
    BulkReviewResult,
    RecordReview,
    RecordReviewUpdate,
    ReviewHistory,
)
from app.services import analysis, artifacts, custody, exports, library, previews, reports, review

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

EXPORT_SHA256_HEADER = "X-Vestigo-Export-SHA256"

# Derived files are served by their recorded kind, never by sniffing their contents.
DERIVED_MIME_TYPES = {
    "keyframe_jpeg": "image/jpeg",
    "exiftool_json": "application/json",
    "exiftool_c2pa_json": "application/json",
    "ffprobe_json": "application/json",
    "ffmpeg_scene_output": "text/plain; charset=utf-8",
    "tesseract_tsv": "text/plain; charset=utf-8",
}


@router.post("/upload", status_code=201, response_model=ArtifactUploadResponse)
def upload_artifact(
    services: Services, file: Annotated[UploadFile | None, File()] = None
) -> ArtifactUploadResponse:
    if file is None:
        raise AppError(400, ErrorCode.MISSING_FILE, "No file was provided in the 'file' form field.")
    artifact = artifacts.create_artifact(services, file.file, file.filename)
    return ArtifactUploadResponse(
        artifact_id=artifact.id,
        filename=artifact.original_filename,
        size_bytes=artifact.size_bytes,
        media_type=MediaType(artifact.media_type),
        mime_type=artifact.mime_type,
        sha256=artifact.sha256,
        created_at=artifact.created_at,
    )


@router.get("", response_model=ArtifactList)
def list_artifacts(services: Services, query: Annotated[ArtifactQuery, Query()]) -> ArtifactList:
    """Search, filter, sort, and page the artifact library (12-MILESTONE-2-PLAN.md §3)."""
    with services.db.reader() as session:
        page = library.list_artifacts(session, query)
    return ArtifactList(
        items=page.items,
        total=page.total,
        limit=query.limit,
        offset=query.offset,
        counts_by_review_state=page.counts_by_review_state,
    )


@router.get("/{artifact_id}", response_model=ArtifactDetail)
def get_artifact(services: Services, artifact_id: str) -> ArtifactDetail:
    return artifacts.get_artifact_detail(services.db, artifact_id)


@router.get("/{artifact_id}/content", response_class=FileResponse)
def get_artifact_content(services: Services, artifact_id: str) -> FileResponse:
    """The original file, for preview in the browser."""
    artifact = artifacts.get_artifact(services.db, artifact_id)
    return FileResponse(
        services.storage.resolve(artifact.stored_path),
        media_type=artifact.mime_type,
        filename=artifact.original_filename,
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "no-store",
        },
    )


@router.get("/{artifact_id}/derived/{derived_file_id}/content", response_class=FileResponse)
def get_derived_file_content(services: Services, artifact_id: str, derived_file_id: str) -> FileResponse:
    """A derived file (for example a keyframe thumbnail), for display in the browser."""
    derived = artifacts.get_derived_file(services.db, artifact_id, derived_file_id)
    return FileResponse(
        services.storage.resolve(derived.stored_path),
        media_type=DERIVED_MIME_TYPES.get(derived.kind, "application/octet-stream"),
        filename=Path(derived.stored_path).name,
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "no-store",
        },
    )


@router.patch("/{artifact_id}/review", response_model=ArtifactDetail)
def update_review(services: Services, artifact_id: str, update: ReviewUpdate) -> ArtifactDetail:
    review.update_artifact_review(services.db, artifact_id, update)
    return artifacts.get_artifact_detail(services.db, artifact_id)


@router.post("/review", response_model=BulkReviewResult)
def bulk_review(services: Services, request: BulkReviewRequest) -> BulkReviewResult:
    """Set one review state on up to 200 artifacts. All or nothing (M2-5)."""
    return review.bulk_review(services.db, request)


@router.get("/{artifact_id}/review-history", response_model=ReviewHistory)
def get_review_history(services: Services, artifact_id: str) -> ReviewHistory:
    return review.get_history(services.db, artifact_id)


@router.patch("/{artifact_id}/evidence/{evidence_id}/review", response_model=RecordReview)
def update_record_review(
    services: Services, artifact_id: str, evidence_id: str, update: RecordReviewUpdate
) -> RecordReview:
    """Review one evidence record. Its classification never changes (M2-2)."""
    return review.update_record_review(services.db, artifact_id, evidence_id, update)


@router.patch("/{artifact_id}/duplicate-library", response_model=ArtifactDetail)
def update_duplicate_library(
    services: Services, artifact_id: str, update: DuplicateLibraryUpdate
) -> ArtifactDetail:
    """Include or exclude the artifact from future duplicate searches. Recorded evidence is unchanged."""
    artifacts.set_duplicate_library(services.db, artifact_id, update.included)
    return artifacts.get_artifact_detail(services.db, artifact_id)


@router.post("/{artifact_id}/preview", response_model=PreviewInfo)
def create_playable_preview(services: Services, artifact_id: str) -> PreviewInfo:
    """Create (or return) a re-encoded viewing copy of a video the browser cannot play (D19).
    A viewing aid only: not evidence, excluded from the export package, deleted with the artifact."""
    preview = previews.create_preview(services, artifact_id)
    return _preview_info(preview)


@router.get("/{artifact_id}/preview", response_model=PreviewInfo)
def get_playable_preview(services: Services, artifact_id: str) -> PreviewInfo:
    return _preview_info(previews.get_preview(services, artifact_id))


@router.get("/{artifact_id}/preview/content", response_class=FileResponse)
def get_playable_preview_content(services: Services, artifact_id: str) -> FileResponse:
    """The viewing copy itself, streamed with HTTP Range for playback."""
    preview = previews.get_preview(services, artifact_id)
    return FileResponse(
        services.storage.resolve(preview.stored_path),
        media_type="video/mp4",
        filename="preview.mp4",
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "no-store",
        },
    )


def _preview_info(preview) -> PreviewInfo:
    return PreviewInfo(
        artifact_id=preview.artifact_id,
        sha256=preview.sha256,
        size_bytes=preview.size_bytes,
        width=preview.width,
        height=preview.height,
        created_at=preview.created_at,
    )


@router.get("/{artifact_id}/jobs", response_model=JobHistory)
def get_job_history(services: Services, artifact_id: str) -> JobHistory:
    """Every analysis job of the artifact, newest first."""
    return analysis.job_history(services.db, artifact_id)


@router.delete("/{artifact_id}", response_model=DeletionSummary)
def delete_artifact(services: Services, artifact_id: str) -> DeletionSummary:
    return artifacts.delete_artifact(services, artifact_id)


@router.get("/{artifact_id}/export", response_class=FileResponse)
def export_evidence_package(
    services: Services, artifact_id: str, job_id: str | None = None, include_original: bool = False
) -> FileResponse:
    """ZIP evidence package for the latest finished job, or `job_id` (M2-6). The original upload is
    included only when `include_original=true`."""
    package = exports.build_export(services, artifact_id, job_id, include_original)
    return FileResponse(
        package.path,
        media_type="application/zip",
        filename=package.filename,
        headers={EXPORT_SHA256_HEADER: package.sha256, "Cache-Control": "no-store"},
        background=BackgroundTask(package.path.unlink, missing_ok=True),
    )


@router.get("/{artifact_id}/custody", response_model=CustodyReport)
def get_custody(services: Services, artifact_id: str) -> CustodyReport:
    """The chain of custody recorded by Vestigo on this machine since upload (M4B): upload,
    analysis jobs, review changes, exports, library changes, and previews, merged chronologically,
    plus every derived file with its recorded lineage. Nothing is inferred or backfilled."""
    return custody.build_custody_report(services.db, artifact_id)


@router.get("/{artifact_id}/evidence", response_model=EvidenceReport)
def get_evidence(
    services: Services, artifact_id: str, job_id: str | None = None, download: bool = False
) -> JSONResponse:
    """Evidence report for the latest finished job, or for `job_id`."""
    report = reports.build_report(services.db, artifact_id, job_id)
    headers = {}
    if download:
        # Both IDs are validated (letters, digits, underscore), so they are safe in a header.
        filename = f"vestigo-evidence-{report.artifact_id}-{report.job_id}.json"
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return JSONResponse(report.model_dump(mode="json"), headers=headers)
