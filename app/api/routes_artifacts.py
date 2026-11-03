from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.api.deps import Services
from app.core.errors import AppError
from app.schemas.artifact import (
    ArtifactDetail,
    ArtifactList,
    ArtifactQuery,
    ArtifactUploadResponse,
    DeletionSummary,
    ReviewUpdate,
)
from app.schemas.common import ErrorCode, MediaType
from app.schemas.evidence import EvidenceReport
from app.services import artifacts, library, reports

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


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


@router.patch("/{artifact_id}/review", response_model=ArtifactDetail)
def update_review(services: Services, artifact_id: str, update: ReviewUpdate) -> ArtifactDetail:
    artifacts.update_review(services.db, artifact_id, update)
    return artifacts.get_artifact_detail(services.db, artifact_id)


@router.delete("/{artifact_id}", response_model=DeletionSummary)
def delete_artifact(services: Services, artifact_id: str) -> DeletionSummary:
    return artifacts.delete_artifact(services, artifact_id)


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
