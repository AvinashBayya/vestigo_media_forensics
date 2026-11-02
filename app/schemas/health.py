from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ToolHealth(BaseModel):
    status: Literal["ok", "missing", "error"]
    version: str | None
    used_in: str
    languages: list[str] | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    version: str
    database: Literal["ok", "error"]
    storage: Literal["ok", "error"]
    tools: dict[str, ToolHealth]
    checked_at: datetime
