"""Geospatial helper schemas (Pass 3, D26). Conversions and geometry, never location findings."""

from pydantic import BaseModel

from app.services.geo import GEO_LIMITATIONS


class CoordinateFormatsInfo(BaseModel):
    """One coordinate pair in the notations analysts read. The same point each time."""

    decimal: str
    degrees_minutes_seconds: str
    degrees_decimal_minutes: str
    iso6709: str


class CoordinatePoint(BaseModel):
    """A point Vestigo holds for this artifact, with where it came from."""

    source: str
    latitude: float
    longitude: float
    formats: CoordinateFormatsInfo
    # Set for a point that came from an analyst's location candidate.
    candidate_id: str | None = None


class CoordinatePair(BaseModel):
    """The geometry between two held points. Geometry, not a conclusion."""

    from_source: str
    to_source: str
    distance_metres: float
    bearing_degrees: float


class GeoToolsResponse(BaseModel):
    artifact_id: str
    notice: str
    # Every coordinate Vestigo holds for this artifact: metadata clues and analyst candidates.
    points: list[CoordinatePoint]
    # Pairwise distances, so an analyst can see how far apart their own points are.
    pairs: list[CoordinatePair]
    limitations: list[str] = list(GEO_LIMITATIONS)
    # Offline map data the analyst has supplied, when any is configured.
    offline_map_available: bool = False
    offline_map_path: str | None = None
