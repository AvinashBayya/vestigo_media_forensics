"""FastAPI application factory. Run with: uvicorn app.main:app --host 0.0.0.0 --port 8400"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from app import __version__
from app.api import routes_health
from app.api.deps import AppServices
from app.core.config import Settings, get_settings
from app.core.database import Database
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.storage import Storage
from app.core.tools import ToolRegistry

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, tools: ToolRegistry | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    data_dir = settings.data_dir.resolve()
    services = AppServices(
        settings=settings,
        db=Database(data_dir / "app.db"),
        storage=Storage(data_dir),
        tools=tools or ToolRegistry(),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        services.storage.prepare()
        services.db.initialize()
        # Pillow refuses images above twice this size and warns above it; uploads are checked
        # against the exact limit before Pillow decodes anything.
        Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
        yield
        services.db.dispose()

    app = FastAPI(
        title="Vestigo Media Forensics",
        version=__version__,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.state.services = services
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(routes_health.router)
    app.include_router(api)
    return app


app = create_app()
