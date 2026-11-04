from fastapi import APIRouter

from app.api.deps import Jobs, Services
from app.schemas.analysis import (
    ImageAnalysisRequest,
    JobCreated,
    JobStatusResponse,
    VideoAnalysisRequest,
)
from app.schemas.common import JobStatus
from app.services import analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/image", status_code=202, response_model=JobCreated)
def start_image_analysis(services: Services, jobs: Jobs, request: ImageAnalysisRequest) -> JobCreated:
    job = analysis.start_image_analysis(services.db, jobs, request)
    return JobCreated(job_id=job.id, artifact_id=job.artifact_id, status=JobStatus(job.status))


@router.post("/video", status_code=202, response_model=JobCreated)
def start_video_analysis(services: Services, jobs: Jobs, request: VideoAnalysisRequest) -> JobCreated:
    """Queue the Milestone 3 video pipeline (video.v1)."""
    job = analysis.start_video_analysis(services.db, jobs, request)
    return JobCreated(job_id=job.id, artifact_id=job.artifact_id, status=JobStatus(job.status))


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(services: Services, jobs: Jobs, job_id: str) -> JobStatusResponse:
    return analysis.get_job_status(services.db, job_id, jobs.runner.stage_names)
