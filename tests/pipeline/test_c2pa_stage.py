from fastapi.testclient import TestClient

from app.core.container import AppServices
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import upload_ok
from tests.pipeline.test_runner import records_for, start_analysis


def c2pa_record(client: TestClient, services: AppServices, path, options: dict | None = None):
    artifact_id = upload_ok(client, path)["artifact_id"]
    job_id = start_analysis(client, artifact_id, options)["job_id"]
    return next(r for r in records_for(services, job_id) if r.stage == "c2pa")


def test_c2pa_stage_reports_detection_without_validation(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    record = c2pa_record(client, services, fixtures.c2pa)

    assert record.status == "succeeded"
    assert record.classification == "OBSERVED"
    assert record.payload["present"] is True
    assert record.payload["validation_performed"] is False
    assert any("NOT validated" in limitation for limitation in record.limitations)
    assert any("not proof" in limitation for limitation in record.limitations)


def test_c2pa_stage_without_manifest(client: TestClient, services: AppServices, fixtures: FixtureSet) -> None:
    record = c2pa_record(client, services, fixtures.jpeg)

    assert record.status == "succeeded"
    assert record.payload["present"] is False
    assert record.payload["validation_performed"] is False


def test_malformed_c2pa_makes_the_stage_partial(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    record = c2pa_record(client, services, fixtures.invalid_c2pa)

    assert record.status == "partial"
    assert all(error["type"] == "C2PA_STRUCTURE_WARNING" for error in record.errors)


def test_c2pa_stage_can_be_disabled(client: TestClient, services: AppServices, fixtures: FixtureSet) -> None:
    record = c2pa_record(client, services, fixtures.c2pa, {"c2pa": False})
    assert record.status == "skipped"
