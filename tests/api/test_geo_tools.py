"""Local geospatial helpers (Pass 3, D26): conversions and geometry, never location findings."""

import math

from fastapi.testclient import TestClient

from app.services.geo import distance_metres, formats, initial_bearing_degrees
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error
from tests.pipeline.test_duplicates import analyse


def tools(client: TestClient, artifact_id: str) -> dict:
    response = client.get(f"/api/v1/geo/artifacts/{artifact_id}/tools")
    assert response.status_code == 200, response.text
    return response.json()


def test_coordinate_formats_describe_the_same_point() -> None:
    result = formats(51.5, -0.12)
    assert result.decimal == "51.500000, -0.120000"
    assert result.degrees_minutes_seconds.startswith("51° 30' 0.00\" N")
    assert "W" in result.degrees_minutes_seconds
    assert result.iso6709.endswith("/")
    assert result.iso6709.startswith("+51.500000-000.120000")

    southern = formats(-33.8688, 151.2093)
    assert "S" in southern.degrees_minutes_seconds
    assert "E" in southern.degrees_minutes_seconds


def test_distance_and_bearing_are_plain_geometry() -> None:
    # London to Sydney: about 16,990 km great-circle.
    metres = distance_metres((51.5074, -0.1278), (-33.8688, 151.2093))
    assert 16_900_000 < metres < 17_100_000
    # A point due north is bearing 0; due east is 90.
    assert math.isclose(initial_bearing_degrees((0.0, 0.0), (1.0, 0.0)), 0.0, abs_tol=0.01)
    assert math.isclose(initial_bearing_degrees((0.0, 0.0), (0.0, 1.0)), 90.0, abs_tol=0.01)
    assert distance_metres((51.5, -0.12), (51.5, -0.12)) == 0.0


def test_held_coordinates_are_listed_in_every_notation(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    body = tools(client, artifact_id)

    assert "does not" in body["notice"] or "Nothing here determines" in body["notice"]
    assert "no coordinate is sent anywhere" in body["notice"]
    (point,) = body["points"]
    assert point["source"].startswith("metadata:")
    assert (round(point["latitude"], 4), round(point["longitude"], 4)) == (51.5, -0.12)
    assert point["formats"]["decimal"] == "51.500000, -0.120000"
    assert point["candidate_id"] is None
    assert body["pairs"] == []  # one point, so no geometry between points

    text = " ".join(body["limitations"]).lower()
    assert "neither is evidence about where media was captured" in text
    assert "vestigo never decides a location" in text


def test_an_analyst_candidate_adds_a_point_and_its_distance(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    client.post(
        f"/api/v1/artifacts/{artifact_id}/location-candidates",
        json={
            "description": "Near the harbour",
            "basis": "IPTC city tag",
            "analyst_assessment": "possible",
            "latitude": 51.51,
            "longitude": -0.13,
        },
    )
    body = tools(client, artifact_id)

    sources = [point["source"] for point in body["points"]]
    assert any(source.startswith("metadata:") for source in sources)
    assert any(source.startswith("candidate: Near the harbour") for source in sources)
    candidate = next(point for point in body["points"] if point["candidate_id"])
    assert candidate["candidate_id"].startswith("loc_")

    (pair,) = body["pairs"]
    # Roughly 1.3 km apart; the point is that it is geometry, reported with a bearing.
    assert 500 < pair["distance_metres"] < 3000
    assert 0.0 <= pair["bearing_degrees"] < 360.0


def test_a_flagged_coordinate_is_never_used_for_geometry(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.with_invalid_location)
    body = tools(client, artifact_id)

    # The out-of-range value stays in the evidence as written, but is not a usable point.
    assert body["points"] == []
    assert body["pairs"] == []
    section = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["location_clues"]
    assert section["coordinates"][0]["valid"] is False
    assert section["coordinates"][0]["latitude"] == 191.5


def test_candidates_without_coordinates_are_skipped(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.png)
    client.post(
        f"/api/v1/artifacts/{artifact_id}/location-candidates",
        json={
            "description": "Somewhere coastal",
            "basis": "Gulls audible in a recording",
            "analyst_assessment": "speculative",
        },
    )
    body = tools(client, artifact_id)
    assert body["points"] == []


def test_offline_map_is_absent_unless_the_analyst_supplies_one(
    client: TestClient, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    body = tools(client, artifact_id)
    # Vestigo never downloads map data; with nothing configured, there is none.
    assert body["offline_map_available"] is False
    assert body["offline_map_path"] is None


def test_unknown_artifact_is_refused(client: TestClient) -> None:
    assert_error(client.get(f"/api/v1/geo/artifacts/{'art_' + '0' * 32}/tools"), 404, "ARTIFACT_NOT_FOUND")
    assert_error(client.get("/api/v1/geo/artifacts/not-an-id/tools"), 404, "ARTIFACT_NOT_FOUND")
