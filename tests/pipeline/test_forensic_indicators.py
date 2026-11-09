"""Forensic indicators (Pass 2, D25): encoding and pixel measurements, never editing verdicts."""

from fastapi.testclient import TestClient

from app.core.container import AppServices
from app.services.forensics import FORENSIC_LIMITATIONS
from tests.api.test_evidence import VERDICT_WORDS
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import upload_ok
from tests.pipeline.test_duplicates import analyse, stage_payload
from tests.pipeline.test_runner import records_for
from tests.pipeline.test_video_pipeline import analyse_video


def test_jpeg_quantization_tables_imply_a_quality_for_the_last_save(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse(client, fixtures.jpeg)
    payload = stage_payload(services, job_id, "forensic_indicators")

    assert payload["container"] == "jpeg"
    tables = payload["quantization_tables"]
    assert tables, payload
    for table in tables:
        assert len(table["values"]) == 64
        assert 1 <= table["implied_quality"] <= 100
        assert table["precision"] in (8, 16)
    # The limitation states what that quality does and does not mean.
    text = " ".join(FORENSIC_LIMITATIONS).lower()
    assert "last save only" in text
    assert "says nothing about what happened before" in text


def test_non_jpeg_says_tables_do_not_apply(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse(client, fixtures.png)
    payload = stage_payload(services, job_id, "forensic_indicators")

    assert payload["quantization_tables"] == []
    assert any("JPEG only" in note for note in payload["notes"])
    # Pixel measurements still ran, so the section is useful for any image.
    assert {entry["channel"] for entry in payload["channel_statistics"]} == {"red", "green", "blue"}


def test_channel_statistics_and_decoded_dimensions_are_measured(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse(client, fixtures.with_metadata)
    payload = stage_payload(services, job_id, "forensic_indicators")

    assert (payload["decoded_width"], payload["decoded_height"]) == (640, 480)
    # The fixture's metadata declares the same size, so this is reported as matching.
    assert payload["dimensions_match"] is True
    for entry in payload["channel_statistics"]:
        assert 0.0 <= entry["mean"] <= 255.0
        assert entry["standard_deviation"] >= 0.0
        assert 0 <= entry["minimum"] <= entry["maximum"] <= 255


def test_video_keyframe_spacing_and_packet_sizes_are_distributions(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_video(client, fixtures.video_scenes)
    payload = stage_payload(services, job_id, "forensic_indicators")

    statistics = payload["video_statistics"]
    assert statistics["packets_examined"] > 0
    assert statistics["keyframe_count"] >= 1
    sizes = statistics["packet_size_bytes"]
    assert sizes["minimum"] <= sizes["median"] <= sizes["maximum"]
    assert sizes["count"] == statistics["packets_examined"]
    # No judgement is attached to any of it.
    assert "verdict" not in payload


def test_no_error_level_analysis_and_no_verdict_language(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse(client, fixtures.jpeg)
    section = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["forensic_indicators"]

    method = section["provenance"]["method"].lower()
    assert "error-level analysis is deliberately not implemented" in method
    assert VERDICT_WORDS.search(method) is None
    # The limitations name the misreading they exist to prevent.
    limitations = " ".join(section["provenance"]["limitations"]).lower()
    assert "routinely misread as proof of editing" in limitations
    assert "no threshold" in limitations
    assert section["provenance"]["classification"] == "DERIVED"  # calculated, not observed


def test_forensic_indicators_can_be_switched_off(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    job_id = client.post(
        "/api/v1/analysis/image",
        json={
            "artifact_id": artifact_id,
            "options": {
                "metadata": True,
                "c2pa": True,
                "location_clues": True,
                "structural": True,
                "forensic_indicators": False,
                "ocr": False,
                "duplicate_search": True,
            },
        },
    ).json()["job_id"]
    record = next(r for r in records_for(services, job_id) if r.stage == "forensic_indicators")
    assert record.status == "skipped"
