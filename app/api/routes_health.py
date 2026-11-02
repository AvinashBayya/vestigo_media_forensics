from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__
from app.api.deps import Services
from app.core.clock import utcnow
from app.schemas.health import HealthResponse, ToolHealth

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(services: Services) -> JSONResponse:
    database = "ok" if services.db.is_healthy() else "error"
    storage = "ok" if services.storage.is_healthy() else "error"

    tools: dict[str, ToolHealth] = {}
    m1_tools_ok = True
    for name, tool in services.tools.all_statuses().items():
        spec = services.tools.specs[name]
        tools[name] = ToolHealth(
            status=tool.status,
            version=tool.version,
            used_in=spec.used_in,
            languages=list(tool.languages) if spec.required_languages else None,
            detail=tool.detail,
        )
        if spec.required_in_m1 and tool.status != "ok":
            m1_tools_ok = False

    if database == "error" or storage == "error":
        status, status_code = "error", 503
    elif not m1_tools_ok:
        status, status_code = "degraded", 200
    else:
        status, status_code = "ok", 200

    body = HealthResponse(
        status=status,
        version=__version__,
        database=database,
        storage=storage,
        tools=tools,
        checked_at=utcnow(),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))
