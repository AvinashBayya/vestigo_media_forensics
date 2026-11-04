"""FastAPI application factory. Run with: uvicorn app.main:app --host 0.0.0.0 --port 8400"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from app import __version__
from app.api import routes_analysis, routes_artifacts, routes_health, routes_library, routes_settings
from app.api.upload_limit import UploadSizeLimitMiddleware
from app.core.config import Settings, get_settings
from app.core.container import AppServices
from app.core.database import Database
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.storage import Storage
from app.core.tools import ToolRegistry
from app.pipeline.jobs import JobExecutor
from app.pipeline.runner import PipelineRunner

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    tools: ToolRegistry | None = None,
    runner_factory: Callable[[AppServices], PipelineRunner] = PipelineRunner,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    data_dir = settings.data_dir.resolve()
    services = AppServices(
        settings=settings,
        db=Database(data_dir / "app.db"),
        storage=Storage(data_dir),
        tools=tools or ToolRegistry(),
    )
    jobs = JobExecutor(runner_factory(services), settings.job_mode, settings.job_workers)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        services.storage.prepare()
        services.db.initialize()
        # Pillow refuses images above twice this size and warns above it; uploads are checked
        # against the exact limit before Pillow decodes anything.
        Image.MAX_IMAGE_PIXELS = settings.max_image_pixels
        jobs.recover()
        yield
        jobs.shutdown()
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
    app.state.jobs = jobs
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition", "X-Vestigo-Export-SHA256"],
    )
    app.add_middleware(
        UploadSizeLimitMiddleware,
        path=f"{API_PREFIX}/artifacts/upload",
        max_file_bytes=max(settings.max_upload_bytes, settings.max_video_upload_bytes),
    )

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(routes_health.router)
    api.include_router(routes_artifacts.router)
    api.include_router(routes_analysis.router)
    api.include_router(routes_library.router)
    api.include_router(routes_settings.router)
    app.include_router(api)
    return app


app = create_app()
