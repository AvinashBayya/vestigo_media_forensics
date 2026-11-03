from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.core.container import AppServices
from app.models import ImageFingerprint
from app.services.phash import hamming_distance
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import upload_ok
from tests.pipeline.test_runner import records_for, start_analysis


def analyse(client: TestClient, path) -> tuple[str, str]:
    artifact_id = upload_ok(client, path)["artifact_id"]
    return artifact_id, start_analysis(client, artifact_id)["job_id"]


def stage_payload(services: AppServices, job_id: str, stage: str) -> dict:
    record = next(r for r in records_for(services, job_id) if r.stage == stage)
    assert record.status == "succeeded", record.errors
    return record.payload


def test_perceptual_hash_is_recorded_and_indexed(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse(client, fixtures.jpeg)

    payload = stage_payload(services, job_id, "perceptual_hash")
    assert payload["algorithm"] == "pHash"
    assert payload["bits"] == 64
    with services.db.reader() as session:
        fingerprint = session.scalars(
            select(ImageFingerprint).where(ImageFingerprint.artifact_id == artifact_id)
        ).one()
    assert fingerprint.value_hex == payload["value"]


def test_duplicate_search_finds_exact_identical_and_near_matches(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    original_id, _ = analyse(client, fixtures.jpeg)
    resized_id, _ = analyse(client, fixtures.near_duplicate)
    unrelated_id, _ = analyse(client, fixtures.unrelated)

    _, edited_job = analyse(client, fixtures.edited)
    matches = {m["artifact_id"]: m for m in stage_payload(services, edited_job, "duplicates")["matches"]}
    assert matches[original_id]["match_type"] == "near"
    assert matches[resized_id]["match_type"] == "near"
    assert unrelated_id not in matches

    copy_id, copy_job = analyse(client, fixtures.jpeg)
    payload = stage_payload(services, copy_job, "duplicates")
    by_id = {m["artifact_id"]: m for m in payload["matches"]}
    assert by_id[original_id]["match_type"] == "exact_file"
    assert by_id[original_id]["similarity"] == 1.0
    assert by_id[resized_id]["match_type"] == "visually_identical"
    assert copy_id not in by_id
    assert payload["threshold"] == 10
    assert payload["library_size"] == 4


def test_earlier_unanalysed_upload_of_the_same_file_is_an_exact_match(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    earlier_id = upload_ok(client, fixtures.png)["artifact_id"]

    _, job_id = analyse(client, fixtures.png)

    matches = stage_payload(services, job_id, "duplicates")["matches"]
    assert [(m["artifact_id"], m["match_type"]) for m in matches] == [(earlier_id, "exact_file")]


def test_duplicate_search_can_be_disabled(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    job_id = start_analysis(client, artifact_id, {"duplicate_search": False})["job_id"]

    record = next(r for r in records_for(services, job_id) if r.stage == "duplicates")
    assert record.status == "skipped"


def evidence_report(client: TestClient, artifact_id: str) -> dict:
    response = client.get(f"/api/v1/artifacts/{artifact_id}/evidence")
    assert response.status_code == 200
    return response.json()


def assert_complete_provenance(provenance: dict, stage: str) -> None:
    assert provenance["stage"] == stage
    assert provenance["status"] == "succeeded"
    assert provenance["method"]
    assert provenance["tool"]
    assert provenance["tool_version"]
    assert provenance["source"]
    assert provenance["started_at"] and provenance["completed_at"]
    assert provenance["started_at"] <= provenance["completed_at"]
    assert provenance["limitations"]
    assert provenance["errors"] == []


def test_resized_recompressed_copy_is_reported_as_a_near_duplicate_through_the_api(
    client: TestClient, services: AppServices, fixtures: FixtureSet, tmp_path: Path
) -> None:
    resized = tmp_path / "resized_recompressed.jpg"
    with Image.open(fixtures.jpeg) as original:
        original.resize((original.width // 2, original.height // 2), Image.Resampling.LANCZOS).save(
            resized, quality=50
        )

    original_id, _ = analyse(client, fixtures.jpeg)
    unrelated_id, _ = analyse(client, fixtures.unrelated)
    resized_id, resized_job = analyse(client, resized)

    original_report = evidence_report(client, original_id)
    resized_report = evidence_report(client, resized_id)
    unrelated_report = evidence_report(client, unrelated_id)

    # Each image's pHash is recorded as evidence with full provenance.
    original_hash = original_report["perceptual_hash"]["value"]
    resized_hash = resized_report["perceptual_hash"]["value"]
    unrelated_hash = unrelated_report["perceptual_hash"]["value"]
    for report in (original_report, resized_report, unrelated_report):
        assert_complete_provenance(report["perceptual_hash"]["provenance"], "perceptual_hash")

    duplicates = resized_report["duplicates"]
    threshold = services.settings.phash_max_distance
    distance = hamming_distance(original_hash, resized_hash)
    assert distance <= threshold
    assert hamming_distance(unrelated_hash, resized_hash) > threshold

    # The API returns the original as a perceptual match (not a byte match), and not the unrelated image.
    by_id = {match["artifact_id"]: match for match in duplicates["matches"]}
    assert set(by_id) == {original_id}
    match = by_id[original_id]
    assert match["match_type"] == ("visually_identical" if distance == 0 else "near")
    assert match["distance"] == distance
    assert match["similarity"] == round(1 - distance / 64, 4)
    assert match["filename"] == fixtures.jpeg.name
    assert match["available"] is True
    assert duplicates["threshold"] == threshold
    assert duplicates["library_size"] == 2
    assert duplicates["compared"] == 2
    assert_complete_provenance(duplicates["provenance"], "duplicates")

    # The stored evidence record carries the same distance and threshold.
    payload = stage_payload(services, resized_job, "duplicates")
    assert payload["threshold"] == threshold
    assert [(m["artifact_id"], m["distance"]) for m in payload["matches"]] == [(original_id, distance)]

    # The unrelated image did not match the original either.
    assert unrelated_report["duplicates"]["matches"] == []


def test_duplicate_search_covers_only_artifacts_already_in_the_library(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    # The search is a record of the library at the time the job ran. An earlier artifact's
    # evidence is not rewritten when a copy is added later; re-running its analysis finds it.
    original_id, original_job = analyse(client, fixtures.jpeg)
    resized_id, _ = analyse(client, fixtures.near_duplicate)

    assert stage_payload(services, original_job, "duplicates")["matches"] == []
    assert [m["artifact_id"] for m in evidence_report(client, original_id)["duplicates"]["matches"]] == []

    rerun_job = start_analysis(client, original_id)["job_id"]
    rerun_matches = stage_payload(services, rerun_job, "duplicates")["matches"]
    assert [m["artifact_id"] for m in rerun_matches] == [resized_id]
