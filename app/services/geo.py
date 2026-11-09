"""Local geospatial helpers (Pass 3, D26).

Coordinate conversion and distance arithmetic, done locally with no service and no network. These
are calculations over numbers the analyst can already see: a formatted coordinate is the same
coordinate, and a distance between two points is geometry, not a finding about where media was
captured. Nothing here decides a location, and no map data is fetched.
"""

import math
from dataclasses import asdict, dataclass
from typing import Any

# Mean Earth radius (WGS-84 mean), in metres. Used for great-circle distance only.
EARTH_RADIUS_METRES = 6_371_008.8

GEO_LIMITATIONS: tuple[str, ...] = (
    "These are conversions and distances over coordinates Vestigo already holds. A reformatted "
    "coordinate is the same coordinate, and a distance is geometry - neither is evidence about "
    "where media was captured.",
    "Distances are great-circle distances on a sphere. They ignore terrain and altitude and differ "
    "from a mapped or travelled distance.",
    "Proximity to an analyst's location candidate means the two points are close together. It does "
    "not confirm the candidate, and Vestigo never decides a location.",
    "No map data, tiles, or place names are fetched: nothing is sent anywhere, and no coordinate "
    "leaves this machine unless the analyst opens an external map link themselves.",
)


@dataclass(frozen=True)
class CoordinateFormats:
    """One coordinate pair written the ways analysts read them. Same point, different notation."""

    decimal: str
    degrees_minutes_seconds: str
    degrees_decimal_minutes: str
    iso6709: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dms(value: float, positive: str, negative: str) -> str:
    hemisphere = positive if value >= 0 else negative
    magnitude = abs(value)
    degrees = int(magnitude)
    minutes_full = (magnitude - degrees) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60
    return f"{degrees}° {minutes}' {seconds:.2f}\" {hemisphere}"


def _ddm(value: float, positive: str, negative: str) -> str:
    hemisphere = positive if value >= 0 else negative
    magnitude = abs(value)
    degrees = int(magnitude)
    minutes = (magnitude - degrees) * 60
    return f"{degrees}° {minutes:.4f}' {hemisphere}"


def formats(latitude: float, longitude: float, altitude: float | None = None) -> CoordinateFormats:
    """The same point in the notations analysts use. No rounding beyond display precision."""
    iso = f"{latitude:+010.6f}{longitude:+011.6f}"
    if altitude is not None:
        iso += f"{altitude:+.3f}"
    return CoordinateFormats(
        decimal=f"{latitude:.6f}, {longitude:.6f}",
        degrees_minutes_seconds=f"{_dms(latitude, 'N', 'S')} {_dms(longitude, 'E', 'W')}",
        degrees_decimal_minutes=f"{_ddm(latitude, 'N', 'S')} {_ddm(longitude, 'E', 'W')}",
        iso6709=iso + "/",
    )


def distance_metres(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Great-circle distance between two points, in metres (haversine on a sphere)."""
    lat1, lon1 = math.radians(first[0]), math.radians(first[1])
    lat2, lon2 = math.radians(second[0]), math.radians(second[1])
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    inner = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_METRES * math.asin(min(1.0, math.sqrt(inner)))


def initial_bearing_degrees(first: tuple[float, float], second: tuple[float, float]) -> float:
    """Initial great-circle bearing from the first point to the second, in degrees from north."""
    lat1, lon1 = math.radians(first[0]), math.radians(first[1])
    lat2, lon2 = math.radians(second[0]), math.radians(second[1])
    delta_lon = lon2 - lon1
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
