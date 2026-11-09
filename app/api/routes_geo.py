from fastapi import APIRouter

from app.api.deps import Services
from app.schemas.geo import GeoToolsResponse
from app.services import geo_tools

router = APIRouter(prefix="/geo", tags=["geo"])

GEO_NOTICE = (
    "Coordinate conversions and distances between points Vestigo already holds for this artifact: "
    "metadata clues read as written, and the analyst's own location candidates. Nothing here "
    "determines where media was captured, no coordinate is sent anywhere, and no map data is "
    "fetched."
)


@router.get("/artifacts/{artifact_id}/tools", response_model=GeoToolsResponse)
def get_geo_tools(services: Services, artifact_id: str) -> GeoToolsResponse:
    """Local geospatial helpers for one artifact (Pass 3): every coordinate Vestigo holds, in each
    notation, with the great-circle distance and bearing between each pair. Calculation only."""
    return geo_tools.build_geo_tools(services, artifact_id, GEO_NOTICE)
