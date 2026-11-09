"""Assembles the local geospatial view for one artifact (Pass 3, D26).

Gathers every coordinate Vestigo already holds - the machine-read location clues (D23) and the
analyst's own location candidates - converts each into the notations analysts read, and reports the
geometry between pairs. It adds no new source of truth: a clue stays a clue, a candidate stays an
analyst statement, and no location is ever decided here.
"""

from itertools import combinations
from pathlib import Path

from sqlalchemy import select

from app.core import ids
from app.core.container import AppServices
from app.models import Artifact, EvidenceRecord, LocationCandidate
from app.schemas.geo import CoordinateFormatsInfo, CoordinatePair, CoordinatePoint, GeoToolsResponse
from app.services.errors import artifact_not_found
from app.services.geo import GEO_LIMITATIONS, distance_metres, formats, initial_bearing_degrees


def _point(
    source: str, latitude: float, longitude: float, candidate_id: str | None = None
) -> CoordinatePoint:
    return CoordinatePoint(
        source=source,
        latitude=latitude,
        longitude=longitude,
        formats=CoordinateFormatsInfo(**formats(latitude, longitude).as_dict()),
        candidate_id=candidate_id,
    )


def _offline_map(services: AppServices) -> tuple[bool, str | None]:
    """Offline map data the analyst supplied, if any. Vestigo never downloads map data."""
    configured = getattr(services.settings, "offline_map_path", "") or ""
    if not configured:
        return False, None
    path = Path(configured).expanduser()
    return (path.exists(), str(path))


def build_geo_tools(services: AppServices, artifact_id: str, notice: str) -> GeoToolsResponse:
    if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
        raise artifact_not_found(artifact_id)

    points: list[CoordinatePoint] = []
    with services.db.reader() as session:
        if session.get(Artifact, artifact_id) is None:
            raise artifact_not_found(artifact_id)

        # Machine-read clues from the most recent location_clues record.
        record = session.scalars(
            select(EvidenceRecord)
            .where(
                EvidenceRecord.artifact_id == artifact_id,
                EvidenceRecord.stage == "location_clues",
            )
            .order_by(EvidenceRecord.completed_at.desc(), EvidenceRecord.id.desc())
        ).first()
        if record is not None:
            for coordinate in (record.payload or {}).get("coordinates") or []:
                if not isinstance(coordinate, dict) or not coordinate.get("valid"):
                    continue  # a flagged coordinate is kept as written, never used for geometry
                latitude, longitude = coordinate.get("latitude"), coordinate.get("longitude")
                if isinstance(latitude, int | float) and isinstance(longitude, int | float):
                    points.append(
                        _point(
                            f"metadata: {coordinate.get('source', 'coordinates')}",
                            float(latitude),
                            float(longitude),
                        )
                    )

        # The analyst's own candidates, where they gave coordinates.
        for candidate in session.scalars(
            select(LocationCandidate)
            .where(LocationCandidate.artifact_id == artifact_id)
            .order_by(LocationCandidate.created_at)
        ):
            if candidate.latitude is None or candidate.longitude is None:
                continue
            points.append(
                _point(
                    f"candidate: {candidate.description}",
                    float(candidate.latitude),
                    float(candidate.longitude),
                    candidate.id,
                )
            )

    pairs = [
        CoordinatePair(
            from_source=first.source,
            to_source=second.source,
            distance_metres=round(
                distance_metres((first.latitude, first.longitude), (second.latitude, second.longitude)), 2
            ),
            bearing_degrees=round(
                initial_bearing_degrees(
                    (first.latitude, first.longitude), (second.latitude, second.longitude)
                ),
                2,
            ),
        )
        for first, second in combinations(points, 2)
    ]
    available, path = _offline_map(services)
    return GeoToolsResponse(
        artifact_id=artifact_id,
        notice=notice,
        points=points,
        pairs=pairs,
        limitations=list(GEO_LIMITATIONS),
        offline_map_available=available,
        offline_map_path=path,
    )
