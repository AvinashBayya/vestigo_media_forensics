from typing import Annotated

from fastapi import Depends, Request

from app.core.container import AppServices


def get_services(request: Request) -> AppServices:
    return request.app.state.services


Services = Annotated[AppServices, Depends(get_services)]
