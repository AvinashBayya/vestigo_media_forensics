from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisJob
from app.schemas.analysis import JobSummary
from app.schemas.common import JobStatus


def latest_job(session: Session, artifact_id: str) -> AnalysisJob | None:
    stmt = (
        select(AnalysisJob)
        .where(AnalysisJob.artifact_id == artifact_id)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .limit(1)
    )
    return session.scalar(stmt)


def to_job_summary(job: AnalysisJob) -> JobSummary:
    return JobSummary(
        job_id=job.id,
        status=JobStatus(job.status),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )
