"""Cases and the read-only integration surface (Pass 3, D26)."""

from fastapi.testclient import TestClient

from app.core.container import AppServices
from tests.api.test_custody_m4b import events_for
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_duplicates import analyse


def make_case(client: TestClient, name: str = "Operation Fixture") -> dict:
    response = client.post("/api/v1/cases", json={"name": name, "notes": "Working notes."})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_case_groups_artifacts_without_touching_evidence(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse(client, fixtures.jpeg)
    before = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    case = make_case(client)

    linked = client.put(f"/api/v1/cases/{case['case_id']}/artifacts/{artifact_id}")
    assert linked.status_code == 200, linked.text
    assert linked.json()["artifact_count"] == 1
    assert linked.json()["artifacts"][0]["artifact_id"] == artifact_id

    after = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    assert after["cases"] == [{"case_id": case["case_id"], "name": "Operation Fixture"}]
    # Linking changed organisation only: every evidence section is untouched.
    for key in ("hashes", "metadata", "structural", "review", "review_history"):
        assert after[key] == before[key]

    listed = client.get("/api/v1/cases").json()
    assert "organisation, not evidence" in listed["notice"]
    assert [item["case_id"] for item in listed["cases"]] == [case["case_id"]]


def test_linking_is_custody_trailed_and_idempotent(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    case = make_case(client)
    url = f"/api/v1/cases/{case['case_id']}/artifacts/{artifact_id}"

    client.put(url)
    client.put(url)  # already a member: nothing new recorded
    client.delete(url)

    events = [
        (event.event_type, event.detail.get("case_name")) for event in events_for(services, artifact_id)
    ]
    assert events == [
        ("case_linked", "Operation Fixture"),
        ("case_unlinked", "Operation Fixture"),
    ]
    assert client.get(f"/api/v1/cases/{case['case_id']}").json()["artifact_count"] == 0


def test_deleting_a_case_never_deletes_an_artifact(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.jpeg)
    case = make_case(client)
    client.put(f"/api/v1/cases/{case['case_id']}/artifacts/{artifact_id}")

    assert client.delete(f"/api/v1/cases/{case['case_id']}").status_code == 204
    assert_error(client.get(f"/api/v1/cases/{case['case_id']}"), 404, "NOT_FOUND")
    # The artifact and its evidence survive untouched.
    assert client.get(f"/api/v1/artifacts/{artifact_id}").status_code == 200
    assert client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["cases"] == []


def test_deleting_an_artifact_removes_only_its_links(client: TestClient, fixtures: FixtureSet) -> None:
    first, _ = analyse(client, fixtures.jpeg)
    second, _ = analyse(client, fixtures.png)
    case = make_case(client)
    client.put(f"/api/v1/cases/{case['case_id']}/artifacts/{first}")
    client.put(f"/api/v1/cases/{case['case_id']}/artifacts/{second}")

    summary = client.delete(f"/api/v1/artifacts/{first}").json()
    assert summary["case_links"] == 1
    remaining = client.get(f"/api/v1/cases/{case['case_id']}").json()
    assert [item["artifact_id"] for item in remaining["artifacts"]] == [second]


def test_case_validation(client: TestClient, fixtures: FixtureSet) -> None:
    assert_error(client.post("/api/v1/cases", json={"name": ""}), 422, "VALIDATION_ERROR")
    assert_error(client.post("/api/v1/cases", json={"name": "x", "extra": 1}), 422, "VALIDATION_ERROR")
    case = make_case(client)
    url = f"/api/v1/cases/{case['case_id']}"
    assert_error(client.patch(url, json={"name": None}), 422, "VALIDATION_ERROR")
    renamed = client.patch(url, json={"name": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"
    assert renamed.json()["updated_at"] is not None

    assert_error(client.put(f"{url}/artifacts/{'art_' + '0' * 32}"), 404, "ARTIFACT_NOT_FOUND")
    missing = f"/api/v1/cases/{'case_' + '0' * 32}"
    assert_error(client.get(missing), 404, "NOT_FOUND")


def test_integration_version_is_discoverable_while_disabled(client: TestClient) -> None:
    body = client.get("/api/v1/integration/version").json()

    assert body["enabled"] is False
    assert body["integration_version"] == "1.0"
    assert body["report_schema_version"] == "1.2"
    assert body["schema_revision"]
    assert "read-only" in body["notice"].lower()
    assert "never create, change, re-classify, or delete" in body["notice"]
    # Everything offered is a GET: the surface has no write operation at all.
    assert body["read_only_endpoints"]
    assert all(endpoint.startswith("GET ") for endpoint in body["read_only_endpoints"])


def test_integration_evidence_is_refused_until_enabled(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.jpeg)
    refused = client.get(f"/api/v1/integration/artifacts/{artifact_id}/evidence")
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "INTEGRATION_DISABLED"
    assert "turned off" in refused.json()["error"]["message"]
    assert "read-only" in refused.json()["error"]["message"]


def test_enabled_integration_serves_a_versioned_read_only_envelope(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    case = make_case(client, "Linked case")
    client.put(f"/api/v1/cases/{case['case_id']}/artifacts/{artifact_id}")
    assert client.patch("/api/v1/settings", json={"integration_api_enabled": True}).status_code == 200

    body = client.get(f"/api/v1/integration/artifacts/{artifact_id}/evidence").json()
    assert body["integration_version"] == "1.0"
    assert body["artifact_id"] == artifact_id
    assert body["report"]["schema_version"] == "1.2"
    assert body["report"]["hashes"]["sha256"]
    assert "not a legal chain of custody" in body["custody"]["notice"]
    assert body["cases"] == [{"case_id": case["case_id"], "name": "Linked case"}]

    # Reading writes nothing: no custody event, and the evidence is unchanged.
    custody_events = [event.event_type for event in events_for(services, artifact_id)]
    assert custody_events == ["case_linked"]
    again = client.get(f"/api/v1/integration/artifacts/{artifact_id}/evidence").json()
    again["report"].pop("created_at"), body["report"].pop("created_at")
    assert again["report"] == body["report"]


def test_the_integration_surface_has_no_write_route(client: TestClient, fixtures: FixtureSet) -> None:
    client.patch("/api/v1/settings", json={"integration_api_enabled": True})
    artifact_id, _ = analyse(client, fixtures.jpeg)
    target = f"/api/v1/integration/artifacts/{artifact_id}/evidence"

    # Every write verb is refused by routing itself, not by a permission check.
    for request in (
        client.post(target, json={}),
        client.patch(target, json={}),
        client.put(target, json={}),
        client.delete(target),
        client.post("/api/v1/integration/artifacts", json={}),
    ):
        assert request.status_code in (404, 405), request.status_code
