from app.core.errors import AppError
from app.models import AnalysisJob
from app.schemas.common import ErrorCode


def artifact_not_found(artifact_id: str) -> AppError:
    return AppError(404, ErrorCode.ARTIFACT_NOT_FOUND, "Artifact not found.", {"artifact_id": artifact_id})


def job_not_found(job_id: str) -> AppError:
    return AppError(404, ErrorCode.JOB_NOT_FOUND, "Analysis job not found.", {"job_id": job_id})


def analysis_in_progress(job: AnalysisJob) -> AppError:
    return AppError(
        409,
        ErrorCode.ANALYSIS_IN_PROGRESS,
        "An analysis is already queued or running for this artifact.",
        {"job_id": job.id, "status": job.status},
    )
