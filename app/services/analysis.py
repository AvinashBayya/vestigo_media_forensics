from collections.abc import Callable

from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import __version__
from app.core import ids
from app.core.clock import utcnow
from app.core.database import Database
from app.models import AnalysisJob, Artifact, EvidenceRecord
from app.pipeline.image_pipeline import IMAGE_PIPELINE
from app.pipeline.jobs import JobExecutor
from app.pipeline.video_pipeline import VIDEO_PIPELINE
from app.schemas.analysis import (
    ImageAnalysisRequest,
    JobHistory,
    JobHistoryItem,
    JobStatusResponse,
    JobSummary,
    StageProgress,
    VideoAnalysisRequest,
)
from app.schemas.common import (
    ACTIVE_JOB_STATUSES,
    ErrorBody,
    ErrorCode,
    JobStatus,
    MediaType,
    StageStatus,
)
from app.services.app_settings import editable_settings
from app.services.errors import analysis_in_progress, artifact_not_found, job_not_found, wrong_media_type


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


def _start_analysis(
    db: Database,
    executor: JobExecutor,
    artifact_id: str,
    requested_options: BaseModel | None,
    pipeline: str,
    expected_media_type: MediaType,
    other_endpoint: str,
    default_options: Callable[[Session], BaseModel],
) -> AnalysisJob:
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)
    with db.writer() as session, session.begin():
        artifact = session.get(Artifact, artifact_id)
        if artifact is None:
            raise artifact_not_found(artifact_id)
        if artifact.media_type != expected_media_type:
            raise wrong_media_type(artifact_id, artifact.media_type, other_endpoint)
        existing = active_job(session, artifact_id)
        if existing is not None:
            raise analysis_in_progress(existing)
        # Requests without options use the analyst's defaults from Settings (M2-8).
        options = requested_options if requested_options is not None else default_options(session)
        job = AnalysisJob(
            id=ids.new_id(ids.JOB),
            artifact_id=artifact_id,
            pipeline=pipeline,
            app_version=__version__,
            status=JobStatus.QUEUED,
            options=options.model_dump(),
            created_at=utcnow(),
        )
        session.add(job)
    executor.submit(job.id)
    # In inline job mode the job has already run; return its current state.
    with db.reader() as session:
        return session.get(AnalysisJob, job.id) or job


def start_image_analysis(db: Database, executor: JobExecutor, request: ImageAnalysisRequest) -> AnalysisJob:
    return _start_analysis(
        db,
        executor,
        request.artifact_id,
        request.options if "options" in request.model_fields_set else None,
        IMAGE_PIPELINE,
        MediaType.IMAGE,
        "video",
        lambda session: editable_settings(session)[0].default_analysis_options,
    )


def start_video_analysis(db: Database, executor: JobExecutor, request: VideoAnalysisRequest) -> AnalysisJob:
    return _start_analysis(
        db,
        executor,
        request.artifact_id,
        request.options if "options" in request.model_fields_set else None,
        VIDEO_PIPELINE,
        MediaType.VIDEO,
        "image",
        lambda session: editable_settings(session)[0].default_video_analysis_options,
    )


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

    error = _job_error(job)
    return JobStatusResponse(
        **to_job_summary(job).model_dump(),
        artifact_id=job.artifact_id,
        pipeline=job.pipeline,
        error=error,
        stages=stages,
    )


def _times(record: EvidenceRecord) -> dict:
    return {"started_at": record.started_at, "completed_at": record.completed_at}


def _job_error(job: AnalysisJob) -> ErrorBody | None:
    return (
        ErrorBody(code=ErrorCode(job.error_code), message=job.error_message or "") if job.error_code else None
    )


def job_history(db: Database, artifact_id: str) -> JobHistory:
    """Every analysis job of an artifact, newest first, with its problem count."""
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)
    problems = (
        select(
            EvidenceRecord.job_id,
            func.sum(
                case((EvidenceRecord.status.in_((StageStatus.FAILED, StageStatus.PARTIAL)), 1), else_=0)
            ),
        )
        .where(EvidenceRecord.artifact_id == artifact_id)
        .group_by(EvidenceRecord.job_id)
    )
    with db.reader() as session:
        if session.get(Artifact, artifact_id) is None:
            raise artifact_not_found(artifact_id)
        jobs = session.scalars(
            select(AnalysisJob)
            .where(AnalysisJob.artifact_id == artifact_id)
            .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        ).all()
        counts = dict(session.execute(problems).all())
    return JobHistory(
        artifact_id=artifact_id,
        jobs=[
            JobHistoryItem(
                **to_job_summary(job).model_dump(),
                pipeline=job.pipeline,
                app_version=job.app_version,
                options=dict(job.options),
                error=_job_error(job),
                problem_count=(counts.get(job.id) or 0) + (1 if job.status == JobStatus.FAILED else 0),
            )
            for job in jobs
        ],
    )
