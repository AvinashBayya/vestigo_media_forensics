"""Duplicate-library management (M2-7): exclusion from future searches, evidence untouched, summary."""

from fastapi.testclient import TestClient

from app.core.container import AppServices
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_duplicates import analyse, stage_payload


def set_included(client: TestClient, artifact_id: str, included: bool) -> dict:
    response = client.patch(f"/api/v1/artifacts/{artifact_id}/duplicate-library", json={"included": included})
    assert response.status_code == 200, response.text
    return response.json()


def test_excluded_artifacts_are_skipped_and_counted(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    original_id, _ = analyse(client, fixtures.jpeg)
    detail = set_included(client, original_id, False)
    assert detail["in_duplicate_library"] is False

    _, copy_job = analyse(client, fixtures.near_duplicate)
    payload = stage_payload(services, copy_job, "duplicates")
    assert payload["matches"] == []
    assert payload["excluded_count"] == 1
    assert payload["library_size"] == 0

    # Byte-identical files are skipped too.
    _, exact_job = analyse(client, fixtures.jpeg)
    exact_matches = stage_payload(services, exact_job, "duplicates")["matches"]
    assert original_id not in {m["artifact_id"] for m in exact_matches}

    report = client.get(f"/api/v1/artifacts/{detail['artifact_id']}/evidence").json()
    assert report["duplicates"]["excluded_count"] == 0  # its own search ran before it was excluded
    provenance = report["duplicates"]["provenance"]
    assert "excluded from duplicate search" in provenance["method"]
    assert any("excluded_count" in item for item in provenance["limitations"])


def test_exclusion_never_rewrites_existing_evidence(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    original_id, _ = analyse(client, fixtures.jpeg)
    copy_id, copy_job = analyse(client, fixtures.near_duplicate)
    before = stage_payload(services, copy_job, "duplicates")
    assert [m["artifact_id"] for m in before["matches"]] == [original_id]

    set_included(client, original_id, False)

    assert stage_payload(services, copy_job, "duplicates") == before
    report = client.get(f"/api/v1/artifacts/{copy_id}/evidence").json()
    assert [m["artifact_id"] for m in report["duplicates"]["matches"]] == [original_id]

    # Re-including makes it searchable again for new analyses.
    set_included(client, original_id, True)
    rerun = client.post("/api/v1/analysis/image", json={"artifact_id": copy_id}).json()["job_id"]
    payload = stage_payload(services, rerun, "duplicates")
    assert [m["artifact_id"] for m in payload["matches"]] == [original_id]
    assert payload["excluded_count"] == 0


def test_excluded_artifacts_do_not_count_as_added_since_analysis(
    client: TestClient, fixtures: FixtureSet
) -> None:
    first_id, _ = analyse(client, fixtures.jpeg)
    later_id = upload_ok(client, fixtures.png)["artifact_id"]
    assert client.get(f"/api/v1/artifacts/{first_id}").json()["added_since_analysis"] == 1

    set_included(client, later_id, False)
    assert client.get(f"/api/v1/artifacts/{first_id}").json()["added_since_analysis"] == 0


def test_duplicate_library_update_validation(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    url = f"/api/v1/artifacts/{artifact_id}/duplicate-library"
    assert_error(client.patch(url, json={}), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"included": "sometimes"}), 422, "VALIDATION_ERROR")
    assert_error(client.patch(url, json={"included": False, "extra": 1}), 422, "VALIDATION_ERROR")
    missing = f"/api/v1/artifacts/{'art_' + '0' * 32}/duplicate-library"
    assert_error(client.patch(missing, json={"included": False}), 404, "ARTIFACT_NOT_FOUND")


def test_library_summary(client: TestClient, services: AppServices, fixtures: FixtureSet) -> None:
    empty = client.get("/api/v1/library/summary").json()
    assert empty["artifact_count"] == 0
    assert empty["storage"] == {"original_bytes": 0, "derived_bytes": 0, "preview_bytes": 0}

    indexed_id, _ = analyse(client, fixtures.jpeg)
    not_indexed_id = upload_ok(client, fixtures.png)["artifact_id"]
    excluded_id, _ = analyse(client, fixtures.unrelated)
    set_included(client, excluded_id, False)

    summary = client.get("/api/v1/library/summary").json()

    assert (
        summary["artifact_count"],
        summary["indexed_count"],
        summary["not_indexed_count"],
        summary["excluded_count"],
    ) == (
        3,
        1,
        1,
        1,
    )
    assert [(a["artifact_id"], a["indexed"]) for a in summary["not_indexed"]] == [(not_indexed_id, False)]
    assert [(a["artifact_id"], a["indexed"]) for a in summary["excluded"]] == [(excluded_id, True)]
    assert summary["not_indexed"][0]["filename"] == fixtures.png.name
    sizes = sum(f.stat().st_size for f in (fixtures.jpeg, fixtures.png, fixtures.unrelated))
    assert summary["storage"]["original_bytes"] == sizes
    derived = services.settings.data_dir / "artifacts"
    on_disk = sum(f.stat().st_size for f in derived.glob("*/derived/*/*"))
    assert summary["storage"]["derived_bytes"] == on_disk > 0
    assert indexed_id
