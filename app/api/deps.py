from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.core.database import Database
from app.core.storage import Storage
from app.core.tools import ToolRegistry


@dataclass
class AppServices:
    settings: Settings
    db: Database
    storage: Storage
    tools: ToolRegistry


def get_services(request: Request) -> AppServices:
    return request.app.state.services


Services = Annotated[AppServices, Depends(get_services)]
