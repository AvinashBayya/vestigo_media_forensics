"""Structural and hidden-data inspection (Pass 2, D25): facts and measurements, never verdicts."""

from fastapi.testclient import TestClient

from app.core.container import AppServices
from app.services.structural import STRUCTURAL_LIMITATIONS, inspect
from tests.api.test_evidence import VERDICT_WORDS
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import upload_ok
from tests.pipeline.test_duplicates import analyse, stage_payload
from tests.pipeline.test_runner import records_for
from tests.pipeline.test_video_pipeline import analyse_video


def findings(payload: dict, kind: str) -> list[dict]:
    return [finding for finding in payload["findings"] if finding["kind"] == kind]


def measurement(payload: dict, name: str) -> dict:
    return next(item for item in payload["measurements"] if item["name"] == name)


def test_clean_file_reports_no_findings_and_says_nothing_about_cleanliness(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse(client, fixtures.jpeg)
    payload = stage_payload(services, job_id, "structural")

    assert payload["container"] == "jpeg"
    assert payload["logical_end"] == payload["file_size"]
    assert payload["trailing_bytes"] == 0
    assert payload["findings"] == []
    # Measurements are still reported: absence of findings is not a clean bill of health.
    assert measurement(payload, "byte_entropy")["value"] > 0
    text = " ".join(STRUCTURAL_LIMITATIONS).lower()
    assert "never reports that a file is clean" in text
    assert "cannot detect well-implemented steganography" in text


def test_data_after_the_end_of_a_jpeg_is_located_and_sized(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse(client, fixtures.appended_jpeg)
    payload = stage_payload(services, job_id, "structural")

    (trailing,) = findings(payload, "trailing_data")
    assert trailing["offset"] == payload["logical_end"]
    assert trailing["size"] == payload["file_size"] - payload["logical_end"] > 0
    assert "follow the end of the jpeg data" in trailing["detail"]


def test_an_appended_archive_shows_as_trailing_data_and_signatures(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse(client, fixtures.png_with_zip)
    payload = stage_payload(services, job_id, "structural")

    assert payload["container"] == "png"
    assert findings(payload, "trailing_data")
    signatures = findings(payload, "embedded_signature")
    kinds = {finding["detail"].split(" signature")[0] for finding in signatures}
    assert {"zip_entry", "zip_end_of_central_directory"} <= kinds
    # Every signature hit is placed, so an analyst can look at exactly those bytes.
    assert all(finding["offset"] >= payload["logical_end"] for finding in signatures)
    # The PNG chunk inventory is reported with its CRCs verified.
    types = {entry["type"] for entry in payload["inventory"]}
    assert {"IHDR", "IEND"} <= types
    assert all(entry["crc_ok"] for entry in payload["inventory"])


def test_oversized_comment_segment_is_reported(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse(client, fixtures.jpeg_big_comment)
    payload = stage_payload(services, job_id, "structural")

    (comment,) = findings(payload, "large_comment_segment")
    assert comment["size"] == 5000
    assert payload["trailing_bytes"] == 0  # the payload is inside the file, not appended


def test_image_bit_measurements_carry_their_method_and_caveat(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse(client, fixtures.png)
    payload = stage_payload(services, job_id, "structural")

    ratio = measurement(payload, "lsb_ones_ratio")
    assert 0.0 <= ratio["value"] <= 1.0
    assert "least-significant bit" in ratio["method"]
    # The caveat is explicit: this number does not distinguish concealment.
    assert "distinguishes neither" in ratio["note"]
    chi = measurement(payload, "lsb_chi_square")
    assert "no threshold here" in chi["note"]


def test_video_and_audio_are_inspected_too(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, video_job = analyse_video(client, fixtures.video_static)
    video = stage_payload(services, video_job, "structural")
    assert video["container"] == "iso_media"
    assert {"ftyp", "moov"} <= {entry["type"] for entry in video["inventory"]}
    assert video["trailing_bytes"] == 0

    artifact_id = upload_ok(client, fixtures.audio_wav)["artifact_id"]
    audio_job = client.post("/api/v1/analysis/audio", json={"artifact_id": artifact_id}).json()["job_id"]
    audio = stage_payload(services, audio_job, "structural")
    assert audio["container"] == "riff"
    assert measurement(audio, "byte_entropy")["value"] > 0


def test_unparsed_container_says_so_instead_of_pretending(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.audio_mp3)["artifact_id"]
    job_id = client.post("/api/v1/analysis/audio", json={"artifact_id": artifact_id}).json()["job_id"]
    record = next(r for r in records_for(services, job_id) if r.stage == "structural")

    # Not parsing a container is a scope note, not a problem: the stage did all it claims to do.
    assert record.status == "succeeded"
    assert record.errors == []
    assert "not structurally parsed by Vestigo" in record.payload["notes"][0]
    assert "ran in full" in record.payload["notes"][0]
    # Byte statistics still ran, so the section is useful rather than empty.
    assert measurement(record.payload, "byte_entropy")["value"] > 0


def test_report_section_and_raw_output_with_no_verdict_language(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse(client, fixtures.png_with_zip)
    section = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["structural"]

    assert section["container"] == "png"
    assert section["binwalk_ran"] is False  # absent in this image; the fact is recorded either way
    kinds = {file["kind"] for file in section["provenance"]["derived_files"]}
    assert "structural_report" in kinds  # the full report is kept as auditable derived evidence

    # The findings and measurements - the data an analyst reads as results - claim nothing.
    data = " ".join(
        [
            *(finding.get("detail") or "" for finding in section["findings"]),
            *(item["method"] + " " + (item.get("note") or "") for item in section["measurements"]),
            section["provenance"]["method"],
        ]
    ).lower()
    match = VERDICT_WORDS.search(data)
    assert match is None, f"verdict language in the structural section: {match.group(0)!r}"
    for claim in ("steganography detected", "file is clean", "hidden data found"):
        assert claim not in data, claim

    # The limitations, by contrast, must name those claims in order to deny them.
    limitations = " ".join(section["provenance"]["limitations"]).lower()
    assert "never reports that a file is clean" in limitations
    assert "not a finding that anything is hidden" in limitations
    assert job_id


def test_structural_can_be_switched_off(
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
                "structural": False,
                "ocr": False,
                "duplicate_search": True,
            },
        },
    ).json()["job_id"]
    record = next(r for r in records_for(services, job_id) if r.stage == "structural")
    assert record.status == "skipped"
    assert "structural" in record.payload["skip_reason"]


def test_inspect_is_read_only(fixtures: FixtureSet) -> None:
    before = fixtures.appended_jpeg.read_bytes()
    report = inspect(fixtures.appended_jpeg)
    assert report.trailing_bytes > 0
    assert fixtures.appended_jpeg.read_bytes() == before  # the original is never modified
