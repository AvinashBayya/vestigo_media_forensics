from typing import Annotated

from fastapi import Depends, Request

from app.core.container import AppServices
from app.pipeline.jobs import JobExecutor


def get_services(request: Request) -> AppServices:
    return request.app.state.services


def get_jobs(request: Request) -> JobExecutor:
    return request.app.state.jobs


Services = Annotated[AppServices, Depends(get_services)]
Jobs = Annotated[JobExecutor, Depends(get_jobs)]
