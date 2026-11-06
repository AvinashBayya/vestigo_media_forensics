from fastapi.testclient import TestClient

from app.core.container import AppServices
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import upload_ok
from tests.pipeline.test_runner import records_for, start_analysis


def c2pa_record(client: TestClient, services: AppServices, path, options: dict | None = None):
    artifact_id = upload_ok(client, path)["artifact_id"]
    job_id = start_analysis(client, artifact_id, options)["job_id"]
    return next(r for r in records_for(services, job_id) if r.stage == "c2pa")


def test_c2pa_stage_detects_and_validates(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    record = c2pa_record(client, services, fixtures.c2pa)

    assert record.status == "succeeded"
    assert record.classification == "OBSERVED"
    assert record.payload["present"] is True
    # Since Milestone 4 the manifest store is validated locally (D20).
    assert record.payload["validation_performed"] is True
    assert record.payload["status"] == "valid"
    assert record.payload["manifest_count"] == 1
    assert record.payload["validator"].startswith("c2pa-python")
    assert any("does NOT prove" in limitation for limitation in record.limitations)
    assert any("No trust list is configured" in limitation for limitation in record.limitations)


def test_c2pa_stage_without_manifest(client: TestClient, services: AppServices, fixtures: FixtureSet) -> None:
    record = c2pa_record(client, services, fixtures.jpeg)

    assert record.status == "succeeded"
    assert record.payload["present"] is False
    assert record.payload["status"] == "absent"
    assert record.payload["manifest_count"] == 0
    assert any("Absence of C2PA data is normal" in item for item in record.limitations)


def test_malformed_c2pa_makes_the_stage_partial(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    record = c2pa_record(client, services, fixtures.invalid_c2pa)

    assert record.status == "partial"
    error_types = {error["type"] for error in record.errors}
    # The fake JUMBF structure is detected, and the validator's inability to read it is recorded.
    assert error_types == {"C2PA_STRUCTURE_WARNING", "C2PA_VALIDATION_UNAVAILABLE"}
    assert record.payload["status"] == "unverifiable"


def test_c2pa_stage_can_be_disabled(client: TestClient, services: AppServices, fixtures: FixtureSet) -> None:
    record = c2pa_record(client, services, fixtures.c2pa, {"c2pa": False})
    assert record.status == "skipped"
