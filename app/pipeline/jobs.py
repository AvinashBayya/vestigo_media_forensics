"""In-process job executor. Job state lives in SQLite; this only decides where `run_job` executes."""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from app.core.logging import exception_location, get_logger, log_event
from app.pipeline.runner import PipelineRunner

logger = get_logger("jobs")


class JobExecutor:
    def __init__(self, runner: PipelineRunner, mode: Literal["thread", "inline"], workers: int) -> None:
        self.runner = runner
        self._pool = (
            ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vestigo-job")
            if mode == "thread"
            else None
        )

    def submit(self, job_id: str) -> None:
        if self._pool is None:
            self._run(job_id)
        else:
            self._pool.submit(self._run, job_id)

    def recover(self) -> None:
        for job_id in self.runner.recover_interrupted_jobs():
            self.submit(job_id)

    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)

    def _run(self, job_id: str) -> None:
        try:
            self.runner.run_job(job_id)
        except Exception as exc:  # noqa: BLE001 - the job stays queued and is retried at startup
            log_event(
                logger,
                logging.ERROR,
                "job.not_started",
                job_id=job_id,
                error_type=type(exc).__name__,
                location=exception_location(exc),
            )
