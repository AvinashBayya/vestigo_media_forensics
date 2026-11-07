"""Location clues stage (M6, D23): clues read as written, never a location claim."""

from fastapi.testclient import TestClient

from app.core.container import AppServices
from app.services.location import LOCATION_LIMITATIONS
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import upload_ok
from tests.pipeline.test_duplicates import analyse, stage_payload
from tests.pipeline.test_runner import records_for
from tests.pipeline.test_video_pipeline import analyse_video


def clues_for(client: TestClient, services: AppServices, path, kind: str = "image") -> dict:
    if kind == "video":
        _, job_id = analyse_video(client, path)
    elif kind == "audio":
        artifact_id = upload_ok(client, path)["artifact_id"]
        job_id = client.post("/api/v1/analysis/audio", json={"artifact_id": artifact_id}).json()["job_id"]
    else:
        _, job_id = analyse(client, path)
    return stage_payload(services, job_id, "location_clues")


def test_gps_is_decimal_and_as_written_with_city_and_device(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    payload = clues_for(client, services, fixtures.with_metadata)

    (coordinate,) = payload["coordinates"]
    # The hemisphere refs are applied for the decimal value (W -> negative), and the original
    # string is kept beside it with its ref.
    assert (coordinate["latitude"], coordinate["longitude"]) == (51.5, -0.12)
    assert coordinate["valid"] is True and coordinate["problem"] is None
    assert "51 deg 30" in coordinate["latitude_as_written"]
    assert "North" in coordinate["latitude_as_written"]

    assert {"tag": "IPTC:City", "value": "Testville"} in payload["text_clues"]
    assert any(entry["tag"] == "EXIF:DateTimeOriginal" for entry in payload["timestamps"])
    device = {entry["tag"]: entry["value"] for entry in payload["device"]}
    assert device["EXIF:Make"] == "VestigoTestCam"
    assert device["EXIF:Model"] == "Fixture Model 1"


def test_southern_hemisphere_altitude_and_xmp_text(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    payload = clues_for(client, services, fixtures.with_southern_location)

    (coordinate,) = payload["coordinates"]
    assert (coordinate["latitude"], coordinate["longitude"]) == (-33.8688, 151.2093)
    assert coordinate["valid"] is True
    assert payload["altitude_meters"] == 58.4
    assert payload["altitude_reference"] == "Above Sea Level"
    assert payload["altitude_as_written"]

    text = {entry["value"] for entry in payload["text_clues"]}
    assert {"Harbourtown", "Fixtureland"} <= text
    assert any(entry["tag"] == "EXIF:GPSDateStamp" for entry in payload["timestamps"])


def test_out_of_range_coordinates_are_flagged_and_kept(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse(client, fixtures.with_invalid_location)
    # The record is partial (a flagged value), so read it directly rather than via stage_payload.
    record = next(r for r in records_for(services, job_id) if r.stage == "location_clues")
    (coordinate,) = record.payload["coordinates"]
    assert coordinate["valid"] is False
    assert "outside ±90" in coordinate["problem"]
    assert coordinate["latitude"] == 191.5  # kept exactly as written, never corrected or dropped
    assert "191 deg" in coordinate["latitude_as_written"]

    # The stage is partial with a recorded warning, not a failure: an unusable value is a finding.
    assert record.status == "partial"
    assert [error["type"] for error in record.errors] == ["LOCATION_VALUE_UNUSABLE"]
    assert artifact_id


def test_video_container_location_is_parsed(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    payload = clues_for(client, services, fixtures.video_with_location, "video")

    assert any(
        (coordinate["latitude"], coordinate["longitude"]) == (51.5, -0.12)
        for coordinate in payload["coordinates"]
    )
    # The container tag itself is recorded as written, with the tag it came from.
    assert payload["iso6709"]
    assert all("GPSCoordinates" in entry["tag"] for entry in payload["iso6709"])


def test_media_without_location_says_so_without_warnings(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse(client, fixtures.png)
    payload = stage_payload(services, job_id, "location_clues")
    assert payload["coordinates"] == []
    assert payload["text_clues"] == []
    assert payload["altitude_meters"] is None

    # Absence is not a problem: the stage succeeds with no warnings.
    record = next(r for r in records_for(services, job_id) if r.stage == "location_clues")
    assert record.status == "succeeded"
    assert record.errors == []


def test_audio_runs_metadata_only_clues(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    payload = clues_for(client, services, fixtures.audio_mp3, "audio")
    # Audio has no visual analysis: metadata-derived observations only, and this fixture has none.
    assert payload["coordinates"] == []
    assert payload["ocr_available"] is False


def test_stage_records_limitations_and_raw_output(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse(client, fixtures.with_metadata)
    record = next(r for r in records_for(services, job_id) if r.stage == "location_clues")

    assert record.classification == "OBSERVED"
    assert record.tool == "ExifTool"
    assert list(record.limitations) == list(LOCATION_LIMITATIONS)
    assert any("never proof of where media was captured" in text for text in record.limitations)
    assert any("Absence of location data is normal" in text for text in record.limitations)
    assert any("No place names are extracted" in text for text in record.limitations)

    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    section = report["location_clues"]
    assert section["coordinates"][0]["latitude"] == 51.5
    kinds = {file["kind"] for file in section["provenance"]["derived_files"]}
    assert kinds == {"exiftool_location_json"}


def test_ocr_text_is_pointed_at_never_interpreted(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    # An image whose OCR finds text: the section flags that text exists for the analyst to read...
    text_id, _ = analyse(client, fixtures.ocr_text)
    with_text = client.get(f"/api/v1/artifacts/{text_id}/evidence").json()["location_clues"]
    assert with_text["ocr_available"] is True
    # ...and never turns that text into place names or any other clue.
    assert with_text["text_clues"] == []
    assert with_text["coordinates"] == []

    # An image with no OCR text says so.
    blank_id, _ = analyse(client, fixtures.png)
    assert (
        client.get(f"/api/v1/artifacts/{blank_id}/evidence").json()["location_clues"]["ocr_available"]
        is False
    )


def test_location_clues_can_be_switched_off(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.with_metadata)["artifact_id"]
    job_id = client.post(
        "/api/v1/analysis/image",
        json={
            "artifact_id": artifact_id,
            "options": {
                "metadata": True,
                "c2pa": True,
                "location_clues": False,
                "ocr": False,
                "duplicate_search": True,
            },
        },
    ).json()["job_id"]

    record = next(r for r in records_for(services, job_id) if r.stage == "location_clues")
    assert record.status == "skipped"
    assert "location_clues" in record.payload["skip_reason"]
    assert client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["location_clues"] is not None
