"""Runs a pipeline for one analysis job and records one evidence record per stage."""

import logging
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.core import ids
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.logging import exception_location, get_logger, log_event
from app.models import AnalysisJob, Artifact, DerivedFile, EvidenceRecord
from app.pipeline.base import (
    AnalysisStage,
    ArtifactView,
    DerivedFileWriter,
    LibraryReader,
    StageContext,
    StageResult,
)
from app.pipeline.image_pipeline import IMAGE_PIPELINE, IMAGE_STAGES
from app.schemas.analysis import AnalysisOptions
from app.schemas.common import ErrorCode, JobStatus, ReviewState, StageStatus

logger = get_logger("pipeline")

PIPELINES: dict[str, Sequence[AnalysisStage]] = {IMAGE_PIPELINE: IMAGE_STAGES}


@dataclass(frozen=True)
class ClaimedJob:
    artifact: ArtifactView
    options: AnalysisOptions
    pipeline: str


class PipelineRunner:
    def __init__(
        self, services: AppServices, pipelines: Mapping[str, Sequence[AnalysisStage]] | None = None
    ) -> None:
        self.services = services
        self.pipelines = pipelines if pipelines is not None else PIPELINES

    def stage_names(self, pipeline: str) -> list[str]:
        return [stage.name for stage in self.pipelines.get(pipeline, ())]

    def run_job(self, job_id: str) -> None:
        claimed = self._claim(job_id)
        if claimed is None:
            return
        log_event(logger, logging.INFO, "job.started", job_id=job_id, artifact_id=claimed.artifact.id)
        try:
            results = self._run_stages(job_id, claimed)
        except Exception as exc:  # noqa: BLE001 - a crash must leave the job visibly failed
            log_event(
                logger,
                logging.ERROR,
                "job.crashed",
                job_id=job_id,
                error_type=type(exc).__name__,
                location=exception_location(exc),
            )
            self._finish(
                job_id,
                JobStatus.FAILED,
                ErrorCode.INTERNAL_ERROR,
                f"Analysis stopped unexpectedly ({type(exc).__name__}).",
            )
            return

        problems = [r for r in results if r.status in (StageStatus.FAILED, StageStatus.PARTIAL)]
        status = JobStatus.COMPLETED_WITH_ERRORS if problems else JobStatus.COMPLETED
        self._finish(job_id, status)
        log_event(logger, logging.INFO, "job.finished", job_id=job_id, status=status)

    def recover_interrupted_jobs(self) -> list[str]:
        """Fail jobs left running by a restart; return queued jobs so they can be resubmitted."""
        with self.services.db.writer() as session, session.begin():
            for job in session.scalars(select(AnalysisJob).where(AnalysisJob.status == JobStatus.RUNNING)):
                job.status = JobStatus.FAILED
                job.completed_at = utcnow()
                job.error_code = ErrorCode.INTERRUPTED
                job.error_message = "The service restarted while this analysis was running. Run it again."
            queued = session.scalars(
                select(AnalysisJob.id)
                .where(AnalysisJob.status == JobStatus.QUEUED)
                .order_by(AnalysisJob.created_at)
            ).all()
        return list(queued)

    def _claim(self, job_id: str) -> ClaimedJob | None:
        storage = self.services.storage
        with self.services.db.writer() as session, session.begin():
            job = session.get(AnalysisJob, job_id)
            if job is None or job.status != JobStatus.QUEUED:
                return None
            artifact = session.get(Artifact, job.artifact_id)
            if artifact is None:
                return None
            job.status = JobStatus.RUNNING
            job.started_at = utcnow()
            return ClaimedJob(
                artifact=ArtifactView(
                    id=artifact.id,
                    path=storage.resolve(artifact.stored_path),
                    media_type=artifact.media_type,
                    mime_type=artifact.mime_type,
                    sha256=artifact.sha256,
                    md5=artifact.md5,
                    size_bytes=artifact.size_bytes,
                ),
                options=AnalysisOptions.model_validate(job.options),
                pipeline=job.pipeline,
            )

    def _run_stages(self, job_id: str, claimed: ClaimedJob) -> list[StageResult]:
        services = self.services
        stages = self.pipelines[claimed.pipeline]
        derived = DerivedFileWriter(services.storage, claimed.artifact.id, job_id)
        results: list[StageResult] = []
        with tempfile.TemporaryDirectory(dir=services.storage.tmp_dir) as scratch:
            ctx = StageContext(
                job_id=job_id,
                options=claimed.options,
                settings=services.settings,
                tools=services.tools,
                derived=derived,
                library=LibraryReader(services.db),
                scratch_dir=Path(scratch),
            )
            for stage in stages:
                result = stage.run(claimed.artifact, ctx)
                ctx.results[stage.name] = result
                self._record(stage, result, claimed.artifact.id, job_id, derived)
                results.append(result)
                log_event(
                    logger,
                    logging.INFO,
                    "stage.finished",
                    job_id=job_id,
                    stage=stage.name,
                    status=result.status,
                    error_type=",".join(error.type for error in result.errors) or None,
                )
        return results

    def _record(
        self,
        stage: AnalysisStage,
        result: StageResult,
        artifact_id: str,
        job_id: str,
        derived: DerivedFileWriter,
    ) -> None:
        with self.services.db.writer() as session, session.begin():
            record = EvidenceRecord(
                id=ids.new_id(ids.EVIDENCE),
                artifact_id=artifact_id,
                job_id=job_id,
                stage=result.stage,
                status=result.status,
                classification=result.classification,
                method=result.method,
                source=result.source,
                tool=result.tool,
                tool_version=result.tool_version,
                payload=result.output,
                errors=[error.model_dump() for error in result.errors],
                limitations=result.limitations,
                review_state=ReviewState.UNREVIEWED,
                started_at=result.started_at,
                completed_at=result.completed_at,
            )
            session.add(record)
            for pending in derived.take(stage.name):
                session.add(
                    DerivedFile(
                        id=pending.info.derived_file_id,
                        artifact_id=artifact_id,
                        job_id=job_id,
                        stage=stage.name,
                        kind=pending.info.kind,
                        stored_path=pending.stored_path,
                        sha256=pending.info.sha256,
                        size_bytes=pending.info.size_bytes,
                        created_at=result.completed_at,
                    )
                )
            session.flush()
            stage.on_recorded(record, session)

    def _finish(
        self,
        job_id: str,
        status: JobStatus,
        error_code: ErrorCode | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.services.db.writer() as session, session.begin():
            job = session.get(AnalysisJob, job_id)
            if job is None:
                return
            job.status = status
            job.completed_at = utcnow()
            job.error_code = error_code
            job.error_message = error_message
