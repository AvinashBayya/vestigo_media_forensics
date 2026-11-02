from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.container import AppServices
from app.models import ImageFingerprint
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
