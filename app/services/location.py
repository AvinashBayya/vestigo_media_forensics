"""Location clues from embedded metadata (M6, D23).

Everything here is a *clue*, read as written: coordinates, timestamps, device fields, and
location-named text tags, each with the tag it came from. Nothing is reconciled, corrected, or
inferred, and no clue ever means the media was captured at a place. Coordinates are converted to
decimal degrees for display beside the original strings; out-of-range values are flagged, never
dropped or fixed. No place names are extracted from OCR text (that would be inference presented as
observation) — the analyst reviews the OCR panels themselves.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.tools import ToolStatus
from app.services.metadata import run_exiftool_json

# -n prints coordinates and refs as signed numbers; the same read also returns the as-written
# strings for every tag via -s (tag names as stored). Composite tags give the combined GPSPosition.
NUMERIC_ARGS = ("-json", "-G0:1", "-a", "-struct", "-n", "-charset", "filename=utf8")
# A second, print-converted read supplies the human strings Vestigo shows beside the decimals.
AS_WRITTEN_ARGS = ("-json", "-G0:1", "-a", "-struct", "-charset", "filename=utf8")

LATITUDE_LIMIT = 90.0
LONGITUDE_LIMIT = 180.0

# Tags whose values are location names or descriptions, by family. Values pass through as written.
TEXT_TAGS: tuple[str, ...] = (
    "City",
    "Sub-location",
    "Location",
    "Province-State",
    "State",
    "Country",
    "Country-PrimaryLocationName",
    "CountryCode",
    "LocationShownCity",
    "LocationShownSublocation",
    "LocationShownProvinceState",
    "LocationShownCountryName",
    "LocationCreatedCity",
    "LocationCreatedSublocation",
    "LocationCreatedProvinceState",
    "LocationCreatedCountryName",
    "GPSAreaInformation",
    "GPSProcessingMethod",
)

# Timestamps relevant to placing media in time. All reported as written, never decode-verified.
TIME_TAGS: tuple[str, ...] = (
    "DateTimeOriginal",
    "CreateDate",
    "ModifyDate",
    "GPSDateStamp",
    "GPSTimeStamp",
    "GPSDateTime",
    "OffsetTimeOriginal",
    "TimeZone",
    "CreationDate",
)

# Device and capture-orientation fields that help an analyst judge a location claim.
DEVICE_TAGS: tuple[str, ...] = (
    "Make",
    "Model",
    "Software",
    "LensModel",
    "Orientation",
    "GPSImgDirection",
    "GPSImgDirectionRef",
    "GPSDestBearing",
    "GPSSpeed",
    "GPSSpeedRef",
    "GPSHPositioningError",
    "GPSDOP",
    "GPSSatellites",
    "GPSStatus",
    "GPSMeasureMode",
    "GPSMapDatum",
    "HandlerDescription",
    "CompressorName",
)

# ISO 6709 as written into QuickTime/Matroska location tags: +51.5000-000.1200+010.000/
ISO6709 = re.compile(
    r"^(?P<lat>[+-]\d{1,2}(?:\.\d+)?)(?P<lon>[+-]\d{1,3}(?:\.\d+)?)(?P<alt>[+-]\d+(?:\.\d+)?)?/?$"
)
# ExifTool normalises a container's ISO 6709 location into "lat lon [alt]" when read numerically.
NORMALISED_COORDINATES = re.compile(
    r"^(?P<lat>[+-]?\d{1,3}(?:\.\d+)?)\s+(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)(?:\s+(?P<alt>[+-]?\d+(?:\.\d+)?))?$"
)

LOCATION_LIMITATIONS: tuple[str, ...] = (
    "Every value here is read as written in the file. Embedded location data is trivially edited, "
    "copied from another file, or set by software, so it is never proof of where media was "
    "captured or created.",
    "Absence of location data is normal - most cameras have GPS disabled and most platforms strip "
    "it on upload. Absence does NOT mean the location was hidden.",
    "Coordinates are shown in decimal degrees beside the original strings. Out-of-range or "
    "unreadable values are flagged and kept as written; nothing is corrected or normalised.",
    "When metadata sources disagree (for example EXIF GPS against an IPTC city), both are shown as "
    "found. Vestigo does not decide which is right.",
    "Timestamps are as written in the file or container, not decode-verified, and their time zone "
    "may be absent, wrong, or local to an unknown place.",
    "No place names are extracted from text in the media. Visible signs, addresses, and clocks are "
    "for the analyst to read in the OCR evidence; Vestigo does not interpret them.",
)


@dataclass
class Coordinate:
    """One coordinate pair, as read. `valid` is False when a value is out of range or unreadable."""

    source: str
    latitude: float | None
    longitude: float | None
    latitude_as_written: str | None
    longitude_as_written: str | None
    valid: bool
    problem: str | None = None


@dataclass
class LocationClues:
    coordinates: list[Coordinate] = field(default_factory=list)
    altitude_meters: float | None = None
    altitude_as_written: str | None = None
    altitude_reference: str | None = None
    # [{"tag": "IPTC:City", "value": "Testville"}] - values exactly as written.
    text_clues: list[dict[str, str]] = field(default_factory=list)
    timestamps: list[dict[str, str]] = field(default_factory=list)
    device: list[dict[str, str]] = field(default_factory=list)
    iso6709: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _tag_index(record: dict[str, Any]) -> dict[str, Any]:
    """Map bare tag name -> value, keeping the first occurrence, plus "family0:Tag" keys."""
    index: dict[str, Any] = {}
    for key, value in record.items():
        parts = key.split(":")
        if len(parts) < 2:
            continue
        name = parts[-1]
        index.setdefault(name, value)
        index.setdefault(f"{parts[0]}:{name}", value)
    return index


def _qualified_names(record: dict[str, Any], wanted: tuple[str, ...]) -> list[tuple[str, Any]]:
    """Tags whose name is in `wanted`, as ("Family0:Tag", value), in file order, de-duplicated."""
    found: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for key, value in record.items():
        parts = key.split(":")
        if len(parts) < 2 or parts[-1] not in wanted:
            continue
        label = f"{parts[0]}:{parts[-1]}"
        if label in seen:
            continue
        seen.add(label)
        found.append((label, value))
    return found


def _signed(value: float | None, ref: Any) -> float | None:
    """Apply a hemisphere ref to an unsigned value (ExifTool -n gives EXIF GPS unsigned)."""
    if value is None:
        return None
    text = str(ref).strip().upper() if ref is not None else ""
    if text.startswith(("S", "W")) and value > 0:
        return -value
    return value


def _check(value: float | None, limit: float, name: str) -> str | None:
    if value is not None and abs(value) > limit:
        return f"{name} {value:g} is outside ±{limit:g}"
    return None


def _coordinate(
    source: str,
    latitude: Any,
    longitude: Any,
    latitude_text: Any,
    longitude_text: Any,
) -> Coordinate | None:
    """One coordinate pair as read. Out-of-range or half-present values are flagged, never fixed."""
    lat, lon = _as_float(latitude), _as_float(longitude)
    lat_text = str(latitude_text) if latitude_text is not None else None
    lon_text = str(longitude_text) if longitude_text is not None else None
    if lat is None and lon is None and lat_text is None and lon_text is None:
        return None

    problems = [
        problem
        for problem in (
            _check(lat, LATITUDE_LIMIT, "latitude"),
            _check(lon, LONGITUDE_LIMIT, "longitude"),
        )
        if problem is not None
    ]
    if lat is None or lon is None:
        if lat is None and lon is None:
            problems.append("coordinate values are unreadable")
        else:
            problems.append("only one of latitude/longitude is present")
    if problems:
        return Coordinate(source, lat, lon, lat_text, lon_text, False, "; ".join(problems))
    return Coordinate(source, lat, lon, lat_text, lon_text, True, None)


def _container_coordinate(label: str, raw: str) -> Coordinate | None:
    """A container location tag: the raw ISO 6709 string, or ExifTool's normalised "lat lon [alt]"."""
    text = raw.strip()
    match = ISO6709.match(text) or NORMALISED_COORDINATES.match(text)
    if match is None:
        return None  # not a readable location value: nothing to read, and nothing to complain about
    return _coordinate(label, match.group("lat"), match.group("lon"), raw, raw)


def read_location_clues(tool: ToolStatus, path: Path, timeout: float) -> tuple[LocationClues, bytes]:
    """Read location clues with two ExifTool passes: numeric values and the as-written strings."""
    numeric, raw = run_exiftool_json(tool, NUMERIC_ARGS, path, timeout)
    try:
        written, _ = run_exiftool_json(tool, AS_WRITTEN_ARGS, path, timeout)
    except Exception:  # noqa: BLE001 - the as-written pass is for display only; never fail on it
        written = {}

    clues = LocationClues()
    numbers, strings = _tag_index(numeric), _tag_index(written)

    # Composite GPS already carries the hemisphere sign; fall back to the raw EXIF pair plus refs.
    lat_ref, lon_ref = strings.get("GPSLatitudeRef"), strings.get("GPSLongitudeRef")
    latitude = numbers.get("Composite:GPSLatitude")
    longitude = numbers.get("Composite:GPSLongitude")
    if latitude is None and longitude is None:
        latitude = _signed(_as_float(numbers.get("GPSLatitude")), lat_ref)
        longitude = _signed(_as_float(numbers.get("GPSLongitude")), lon_ref)
    latitude_text, longitude_text = strings.get("GPSLatitude"), strings.get("GPSLongitude")
    gps = _coordinate("EXIF/container GPS", latitude, longitude, latitude_text, longitude_text)
    if gps is not None:
        # The hemisphere refs are part of what was written; keep them visible in the strings.
        if gps.latitude_as_written and lat_ref:
            gps.latitude_as_written = f"{gps.latitude_as_written} ({lat_ref})"
        if gps.longitude_as_written and lon_ref:
            gps.longitude_as_written = f"{gps.longitude_as_written} ({lon_ref})"
        clues.coordinates.append(gps)

    # Container location tags (QuickTime/Matroska ISO 6709), recorded as written and parsed if
    # readable. ExifTool may already have normalised the string; both forms are accepted.
    for key, value in numeric.items():
        name = key.split(":")[-1]
        if name not in ("GPSCoordinates", "Location") or not isinstance(value, str):
            continue
        container = _container_coordinate(key, value)
        if container is None:
            continue
        clues.iso6709.append({"tag": key, "value": value})
        if not any(
            existing.latitude == container.latitude and existing.longitude == container.longitude
            for existing in clues.coordinates
        ):
            clues.coordinates.append(container)

    altitude = _as_float(numbers.get("GPSAltitude"))
    if altitude is not None:
        clues.altitude_meters = altitude
        written_altitude = strings.get("GPSAltitude")
        clues.altitude_as_written = str(written_altitude) if written_altitude is not None else None
        reference = strings.get("GPSAltitudeRef")
        clues.altitude_reference = str(reference) if reference is not None else None

    iso_tags = {entry["tag"] for entry in clues.iso6709}
    for label, value in _qualified_names(written, TEXT_TAGS):
        if label in iso_tags or value is None or isinstance(value, dict | list):
            continue
        text = str(value).strip()
        if text:
            clues.text_clues.append({"tag": label, "value": text})
    for label, value in _qualified_names(written, TIME_TAGS):
        if value is not None and not isinstance(value, dict | list):
            clues.timestamps.append({"tag": label, "value": str(value)})
    for label, value in _qualified_names(written, DEVICE_TAGS):
        if value is not None and not isinstance(value, dict | list):
            clues.device.append({"tag": label, "value": str(value)})

    for coordinate in clues.coordinates:
        if not coordinate.valid:
            clues.warnings.append(f"{coordinate.source}: {coordinate.problem}. The value is kept as written.")
    return clues, raw


def location_payload(clues: LocationClues) -> dict[str, Any]:
    """The location_clues stage payload: clue lists exactly as read, each tagged with its source."""
    return {
        "coordinates": [
            {
                "source": coordinate.source,
                "latitude": coordinate.latitude,
                "longitude": coordinate.longitude,
                "latitude_as_written": coordinate.latitude_as_written,
                "longitude_as_written": coordinate.longitude_as_written,
                "valid": coordinate.valid,
                "problem": coordinate.problem,
            }
            for coordinate in clues.coordinates
        ],
        "altitude_meters": clues.altitude_meters,
        "altitude_as_written": clues.altitude_as_written,
        "altitude_reference": clues.altitude_reference,
        "text_clues": clues.text_clues,
        "timestamps": clues.timestamps,
        "device": clues.device,
        "iso6709": clues.iso6709,
        # True when this analysis produced OCR text the analyst can read for visible location clues
        # (set by the stage's caller; no text is ever interpreted here).
        "ocr_available": False,
    }
