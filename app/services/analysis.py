from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.core import ids
from app.core.clock import utcnow
from app.core.database import Database
from app.models import AnalysisJob, Artifact, EvidenceRecord
from app.pipeline.image_pipeline import IMAGE_PIPELINE
from app.pipeline.jobs import JobExecutor
from app.schemas.analysis import ImageAnalysisRequest, JobStatusResponse, JobSummary, StageProgress
from app.schemas.common import ACTIVE_JOB_STATUSES, ErrorBody, ErrorCode, JobStatus, StageStatus
from app.services.errors import analysis_in_progress, artifact_not_found, job_not_found


def latest_job(session: Session, artifact_id: str) -> AnalysisJob | None:
    stmt = (
        select(AnalysisJob)
        .where(AnalysisJob.artifact_id == artifact_id)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .limit(1)
    )
    return session.scalar(stmt)


def active_job(session: Session, artifact_id: str) -> AnalysisJob | None:
    stmt = select(AnalysisJob).where(
        AnalysisJob.artifact_id == artifact_id, AnalysisJob.status.in_(ACTIVE_JOB_STATUSES)
    )
    return session.scalars(stmt).first()


def to_job_summary(job: AnalysisJob) -> JobSummary:
    return JobSummary(
        job_id=job.id,
        status=JobStatus(job.status),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def start_image_analysis(db: Database, executor: JobExecutor, request: ImageAnalysisRequest) -> AnalysisJob:
    artifact_id = request.artifact_id
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)
    with db.writer() as session, session.begin():
        if session.get(Artifact, artifact_id) is None:
            raise artifact_not_found(artifact_id)
        existing = active_job(session, artifact_id)
        if existing is not None:
            raise analysis_in_progress(existing)
        job = AnalysisJob(
            id=ids.new_id(ids.JOB),
            artifact_id=artifact_id,
            pipeline=IMAGE_PIPELINE,
            app_version=__version__,
            status=JobStatus.QUEUED,
            options=request.options.model_dump(),
            created_at=utcnow(),
        )
        session.add(job)
    executor.submit(job.id)
    with db.reader() as session:
        return session.get(AnalysisJob, job.id) or job


def get_job_status(db: Database, job_id: str, stage_names: Callable[[str], list[str]]) -> JobStatusResponse:
    if not ids.is_valid_id(job_id, ids.JOB):
        raise job_not_found(job_id)
    with db.reader() as session:
        job = session.get(AnalysisJob, job_id)
        if job is None:
            raise job_not_found(job_id)
        records = {
            record.stage: record
            for record in session.scalars(select(EvidenceRecord).where(EvidenceRecord.job_id == job_id))
        }

    stages: list[StageProgress] = []
    running_assigned = False
    for name in stage_names(job.pipeline):
        record = records.get(name)
        if record is not None:
            stages.append(StageProgress(stage=name, status=StageStatus(record.status), **_times(record)))
            continue
        if job.status == JobStatus.RUNNING and not running_assigned:
            status, running_assigned = StageStatus.RUNNING, True
        elif job.status in ACTIVE_JOB_STATUSES:
            status = StageStatus.PENDING
        else:
            # The job ended (crash or restart) before this stage ran.
            status = StageStatus.SKIPPED
        stages.append(StageProgress(stage=name, status=status, started_at=None, completed_at=None))

    error = None
    if job.error_code:
        error = ErrorBody(code=ErrorCode(job.error_code), message=job.error_message or "")
    return JobStatusResponse(
        **to_job_summary(job).model_dump(),
        artifact_id=job.artifact_id,
        pipeline=job.pipeline,
        error=error,
        stages=stages,
    )


def _times(record: EvidenceRecord) -> dict:
    return {"started_at": record.started_at, "completed_at": record.completed_at}
