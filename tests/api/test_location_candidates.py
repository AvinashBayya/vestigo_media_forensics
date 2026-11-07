"""Location candidates (M6): analyst statements, custody-trailed, never a Vestigo location claim."""

import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.core.container import AppServices
from tests.api.test_custody_m4b import events_for
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_duplicates import analyse

BASIS = "IPTC city tag says Testville and a street sign is legible in the OCR text."


def record_candidate(client: TestClient, artifact_id: str, **overrides: object) -> dict:
    payload: dict = {
        "description": "Near the harbour, Testville",
        "basis": BASIS,
        "analyst_assessment": "speculative",
        **overrides,
    }
    response = client.post(f"/api/v1/artifacts/{artifact_id}/location-candidates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_candidate_is_recorded_as_an_unverified_analyst_statement(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.with_metadata)["artifact_id"]
    candidate = record_candidate(
        client,
        artifact_id,
        latitude=51.5,
        longitude=-0.12,
        analyst_assessment="possible",
        notes="Matches the EXIF pair, which is itself unverified.",
    )

    assert candidate["candidate_id"].startswith("loc_")
    # An analyst hypothesis, not an external reference and not a machine observation.
    assert candidate["classification"] == "UNVERIFIED"
    assert candidate["review_state"] == "UNREVIEWED"
    assert candidate["analyst_assessment"] == "possible"
    assert (candidate["latitude"], candidate["longitude"]) == (51.5, -0.12)
    assert candidate["basis"] == BASIS
    assert candidate["recorded_at"] and candidate["updated_at"] is None

    listed = client.get(f"/api/v1/artifacts/{artifact_id}/location-candidates").json()
    assert "UNVERIFIED" in listed["notice"]
    assert "never a machine-calculated" in listed["notice"]
    assert "never a finding that the media was captured at that place" in listed["notice"]
    assert [item["candidate_id"] for item in listed["candidates"]] == [candidate["candidate_id"]]

    # The custody event names no coordinates: they are sensitive (05 §7).
    (event,) = events_for(services, artifact_id)
    assert event.event_type == "location_candidate_recorded"
    assert event.detail == {
        "candidate_id": candidate["candidate_id"],
        "analyst_assessment": "possible",
        "has_coordinates": True,
        "support_count": 0,
    }
    assert "51.5" not in json.dumps(event.detail)


def test_assessment_is_required_and_constrained(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    url = f"/api/v1/artifacts/{artifact_id}/location-candidates"

    # The analyst must choose their own label; Vestigo never defaults or derives it.
    assert_error(client.post(url, json={"description": "Somewhere", "basis": BASIS}), 422, "VALIDATION_ERROR")
    for value in ("confirmed", "certain", "0.9", ""):
        assert_error(
            client.post(url, json={"description": "Somewhere", "basis": BASIS, "analyst_assessment": value}),
            422,
            "VALIDATION_ERROR",
        )
    for value in ("speculative", "possible", "likely"):
        assert (
            client.post(
                url, json={"description": "Somewhere", "basis": BASIS, "analyst_assessment": value}
            ).status_code
            == 201
        )


def test_candidate_validation(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    url = f"/api/v1/artifacts/{artifact_id}/location-candidates"
    base = {"description": "Somewhere", "basis": BASIS, "analyst_assessment": "likely"}

    assert_error(client.post(url, json={**base, "description": ""}), 422, "VALIDATION_ERROR")
    assert_error(client.post(url, json={**base, "basis": ""}), 422, "VALIDATION_ERROR")
    # Coordinates are range-validated and must come as a pair.
    assert_error(client.post(url, json={**base, "latitude": 91, "longitude": 0}), 422, "VALIDATION_ERROR")
    assert_error(client.post(url, json={**base, "latitude": 0, "longitude": 181}), 422, "VALIDATION_ERROR")
    assert_error(client.post(url, json={**base, "latitude": 51.5}), 422, "VALIDATION_ERROR")
    assert_error(client.post(url, json={**base, "extra": 1}), 422, "VALIDATION_ERROR")
    missing = f"/api/v1/artifacts/{'art_' + '0' * 32}/location-candidates"
    assert_error(client.post(missing, json=base), 404, "ARTIFACT_NOT_FOUND")


def test_supports_must_belong_to_the_same_artifact(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    other_id, _ = analyse(client, fixtures.png)
    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    evidence_id = report["location_clues"]["provenance"]["evidence_id"]
    derived_id = report["location_clues"]["provenance"]["derived_files"][0]["derived_file_id"]
    foreign_evidence = client.get(f"/api/v1/artifacts/{other_id}/evidence").json()["metadata"]["provenance"][
        "evidence_id"
    ]
    url = f"/api/v1/artifacts/{artifact_id}/location-candidates"
    base = {"description": "Somewhere", "basis": BASIS, "analyst_assessment": "likely"}

    candidate = record_candidate(
        client,
        artifact_id,
        supports=[
            {"type": "evidence_record", "id": evidence_id},
            {"type": "derived_file", "id": derived_id},
        ],
    )
    assert [ref["type"] for ref in candidate["supports"]] == ["evidence_record", "derived_file"]

    # Another artifact's evidence, a non-existent id, and a wrong-prefix id are all refused.
    for support in (
        {"type": "evidence_record", "id": foreign_evidence},
        {"type": "evidence_record", "id": "ev_" + "0" * 32},
        {"type": "derived_file", "id": evidence_id},
        {"type": "external_lead", "id": "lead_" + "0" * 32},
    ):
        assert_error(client.post(url, json={**base, "supports": [support]}), 404, "NOT_FOUND")
    assert_error(
        client.post(url, json={**base, "supports": [{"type": "artifact", "id": artifact_id}]}),
        422,
        "VALIDATION_ERROR",
    )


def test_external_lead_can_support_a_candidate(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    lead = client.post(
        f"/api/v1/artifacts/{artifact_id}/external-leads",
        json={"provider": "TinEye", "result_url": "https://example.org/results/7"},
    ).json()

    candidate = record_candidate(
        client, artifact_id, supports=[{"type": "external_lead", "id": lead["lead_id"]}]
    )
    assert candidate["supports"] == [{"type": "external_lead", "id": lead["lead_id"]}]


def test_edits_are_custody_trailed_and_noops_are_not(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    candidate = record_candidate(client, artifact_id)
    url = f"/api/v1/artifacts/{artifact_id}/location-candidates/{candidate['candidate_id']}"

    updated = client.patch(url, json={"analyst_assessment": "likely", "review_state": "REVIEWED"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["analyst_assessment"] == "likely"
    assert updated.json()["updated_at"] is not None

    noop = client.patch(url, json={"analyst_assessment": "likely"})
    assert noop.status_code == 200
    assert noop.json()["updated_at"] == updated.json()["updated_at"]

    # Coordinates may be added, and cleared, but only as a pair.
    assert client.patch(url, json={"latitude": 10.0, "longitude": 20.0}).status_code == 200
    assert_error(client.patch(url, json={"latitude": 11.0}), 422, "VALIDATION_ERROR")
    cleared = client.patch(url, json={"latitude": None, "longitude": None})
    assert cleared.status_code == 200
    assert (cleared.json()["latitude"], cleared.json()["longitude"]) == (None, None)

    for field in ("description", "basis", "analyst_assessment", "notes", "supports", "review_state"):
        assert_error(client.patch(url, json={field: None}), 422, "VALIDATION_ERROR")

    events = [(event.event_type, event.detail.get("fields")) for event in events_for(services, artifact_id)]
    assert events == [
        ("location_candidate_recorded", None),
        ("location_candidate_updated", ["analyst_assessment", "review_state"]),
        ("location_candidate_updated", ["latitude", "longitude"]),
        ("location_candidate_updated", ["latitude", "longitude"]),
    ]

    assert client.delete(url).status_code == 204
    assert_error(client.patch(url, json={"notes": "x"}), 404, "NOT_FOUND")
    assert client.get(f"/api/v1/artifacts/{artifact_id}/location-candidates").json()["candidates"] == []
    # The trail keeps the whole story, including the deletion.
    assert [event.event_type for event in events_for(services, artifact_id)][-1] == (
        "location_candidate_deleted"
    )


def test_candidates_flow_into_report_export_custody_and_deletion(
    client: TestClient, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    candidate = record_candidate(client, artifact_id, latitude=51.5, longitude=-0.12)

    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    assert [item["candidate_id"] for item in report["location_candidates"]] == [candidate["candidate_id"]]
    assert report["location_candidates"][0]["classification"] == "UNVERIFIED"

    response = client.get(f"/api/v1/artifacts/{artifact_id}/export")
    package = zipfile.ZipFile(io.BytesIO(response.content))
    packaged = json.loads(package.read("report.json"))
    assert packaged["location_candidates"][0]["basis"] == BASIS
    assert packaged["location_clues"]["coordinates"][0]["latitude"] == 51.5
    custody_events = json.loads(package.read("custody.json"))["events"]
    assert "location_candidate_recorded" in [event["type"] for event in custody_events]

    summary = client.delete(f"/api/v1/artifacts/{artifact_id}").json()
    assert summary["location_candidates"] == 1


def test_coordinates_never_reach_the_logs(client: TestClient, fixtures: FixtureSet, caplog) -> None:
    artifact_id = upload_ok(client, fixtures.with_metadata)["artifact_id"]
    with caplog.at_level(0):
        candidate = record_candidate(client, artifact_id, latitude=51.5, longitude=-0.12)
        url = f"/api/v1/artifacts/{artifact_id}/location-candidates/{candidate['candidate_id']}"
        client.patch(url, json={"latitude": 33.8688, "longitude": 151.2093})
        client.delete(url)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "location_candidate.recorded" in logged  # the events are logged...
    for secret in ("51.5", "-0.12", "33.8688", "151.2093", BASIS):
        assert secret not in logged  # ...but never the coordinates or the analyst's words
