from dataclasses import dataclass

from app.core.config import Settings
from app.core.database import Database
from app.core.storage import Storage
from app.core.tools import ToolRegistry


@dataclass
class AppServices:
    """Long-lived objects shared by the API, services, and pipeline."""

    settings: Settings
    db: Database
    storage: Storage
    tools: ToolRegistry
