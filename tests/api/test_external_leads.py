"""External leads (M5): analyst-recorded search results, custody-trailed and never verified."""

import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.core.container import AppServices
from tests.api.test_custody_m4b import events_for
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_duplicates import analyse
from tests.pipeline.test_video_pipeline import analyse_video

RESULT_URL = "https://example.org/results/42"


def record_lead(client: TestClient, artifact_id: str, **overrides: object) -> dict:
    payload: dict = {"provider": "TinEye", "result_url": RESULT_URL, **overrides}
    response = client.post(f"/api/v1/artifacts/{artifact_id}/external-leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_lead_is_recorded_exactly_as_entered(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    claimed = "posted 'around 2019' according to the page footer"
    lead = record_lead(
        client,
        artifact_id,
        image_url="https://example.org/image.jpg",
        claimed_published_at=claimed,
        notes="Found on a news site.",
    )

    assert lead["lead_id"].startswith("lead_")
    assert lead["classification"] == "EXTERNAL"
    assert lead["review_state"] == "UNREVIEWED"
    assert lead["claimed_published_at"] == claimed  # stored exactly as entered, never parsed
    assert lead["recorded_at"] and lead["recorded_at"] != claimed
    assert lead["updated_at"] is None
    assert lead["derived_file_id"] is None

    (event,) = events_for(services, artifact_id)
    assert event.event_type == "lead_recorded"
    assert event.detail == {"lead_id": lead["lead_id"], "provider": "TinEye", "derived_file_id": None}

    listed = client.get(f"/api/v1/artifacts/{artifact_id}/external-leads").json()
    assert "never proof of the original source" in listed["notice"]
    assert [item["lead_id"] for item in listed["leads"]] == [lead["lead_id"]]


def test_video_leads_name_a_real_keyframe(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse_video(client, fixtures.video_static)
    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    keyframe_id = report["keyframes"]["frames"][0]["derived_file_id"]
    metadata_file = report["metadata"]["provenance"]["derived_files"][0]["derived_file_id"]

    # A video lead must say which keyframe was searched...
    assert_error(
        client.post(
            f"/api/v1/artifacts/{artifact_id}/external-leads",
            json={"provider": "TinEye", "result_url": RESULT_URL},
        ),
        422,
        "VALIDATION_ERROR",
    )
    # ...a real one that belongs to this artifact and is actually a keyframe.
    assert_error(
        client.post(
            f"/api/v1/artifacts/{artifact_id}/external-leads",
            json={"provider": "TinEye", "result_url": RESULT_URL, "derived_file_id": "df_" + "0" * 32},
        ),
        404,
        "NOT_FOUND",
    )
    assert_error(
        client.post(
            f"/api/v1/artifacts/{artifact_id}/external-leads",
            json={"provider": "TinEye", "result_url": RESULT_URL, "derived_file_id": metadata_file},
        ),
        422,
        "VALIDATION_ERROR",
    )

    lead = record_lead(client, artifact_id, derived_file_id=keyframe_id)
    assert lead["derived_file_id"] == keyframe_id
    (event,) = [e for e in events_for(services, artifact_id) if e.event_type == "lead_recorded"]
    assert event.detail["derived_file_id"] == keyframe_id


def test_lead_subject_rules_for_images_and_audio(client: TestClient, fixtures: FixtureSet) -> None:
    image_id, _ = analyse(client, fixtures.jpeg)
    report = client.get(f"/api/v1/artifacts/{image_id}/evidence").json()
    some_derived = report["metadata"]["provenance"]["derived_files"][0]["derived_file_id"]
    assert_error(
        client.post(
            f"/api/v1/artifacts/{image_id}/external-leads",
            json={"provider": "TinEye", "result_url": RESULT_URL, "derived_file_id": some_derived},
        ),
        422,
        "VALIDATION_ERROR",
    )

    audio_id = upload_ok(client, fixtures.audio_mp3)["artifact_id"]
    assert_error(
        client.post(
            f"/api/v1/artifacts/{audio_id}/external-leads",
            json={"provider": "TinEye", "result_url": RESULT_URL},
        ),
        422,
        "WRONG_MEDIA_TYPE",
    )


def test_lead_validation(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    url = f"/api/v1/artifacts/{artifact_id}/external-leads"
    assert_error(client.post(url, json={"provider": "TinEye"}), 422, "VALIDATION_ERROR")
    assert_error(
        client.post(url, json={"provider": "TinEye", "result_url": "ftp://example.org/x"}),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(
        client.post(url, json={"provider": "TinEye", "result_url": RESULT_URL, "extra": 1}),
        422,
        "VALIDATION_ERROR",
    )
    missing = f"/api/v1/artifacts/{'art_' + '0' * 32}/external-leads"
    assert_error(
        client.post(missing, json={"provider": "TinEye", "result_url": RESULT_URL}),
        404,
        "ARTIFACT_NOT_FOUND",
    )


def test_lead_edits_are_custody_trailed_and_noops_are_not(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    lead = record_lead(client, artifact_id)
    url = f"/api/v1/artifacts/{artifact_id}/external-leads/{lead['lead_id']}"

    updated = client.patch(url, json={"notes": "Checked twice.", "review_state": "REVIEWED"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["notes"] == "Checked twice."
    assert updated.json()["review_state"] == "REVIEWED"
    assert updated.json()["updated_at"] is not None

    noop = client.patch(url, json={"notes": "Checked twice."})
    assert noop.status_code == 200
    assert noop.json()["updated_at"] == updated.json()["updated_at"]

    types = [(e.event_type, e.detail) for e in events_for(services, artifact_id)]
    assert types == [
        ("lead_recorded", {"lead_id": lead["lead_id"], "provider": "TinEye", "derived_file_id": None}),
        ("lead_updated", {"lead_id": lead["lead_id"], "fields": ["notes", "review_state"]}),
    ]

    assert client.delete(url).status_code == 204
    assert_error(client.patch(url, json={"notes": "x"}), 404, "NOT_FOUND")
    assert client.get(f"/api/v1/artifacts/{artifact_id}/external-leads").json()["leads"] == []
    # The custody trail keeps the full story: recorded, updated, deleted.
    assert [e.event_type for e in events_for(services, artifact_id)] == [
        "lead_recorded",
        "lead_updated",
        "lead_deleted",
    ]


def test_leads_flow_into_report_export_custody_and_deletion(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.jpeg)
    lead = record_lead(client, artifact_id, claimed_published_at="2019-05-01 (page claim)")

    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    assert [item["lead_id"] for item in report["external_leads"]] == [lead["lead_id"]]

    response = client.get(f"/api/v1/artifacts/{artifact_id}/export")
    package = zipfile.ZipFile(io.BytesIO(response.content))
    packaged = json.loads(package.read("report.json"))["external_leads"]
    assert packaged[0]["claimed_published_at"] == "2019-05-01 (page claim)"
    custody_events = json.loads(package.read("custody.json"))["events"]
    assert "lead_recorded" in [event["type"] for event in custody_events]

    summary = client.delete(f"/api/v1/artifacts/{artifact_id}").json()
    assert summary["external_leads"] == 1


def test_download_parameter_serves_an_attachment(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse_video(client, fixtures.video_static)
    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    keyframe_id = report["keyframes"]["frames"][0]["derived_file_id"]

    inline = client.get(f"/api/v1/artifacts/{artifact_id}/derived/{keyframe_id}/content")
    assert inline.headers["content-disposition"].startswith("inline")

    attached = client.get(
        f"/api/v1/artifacts/{artifact_id}/derived/{keyframe_id}/content", params={"download": "true"}
    )
    assert attached.status_code == 200
    assert attached.headers["content-disposition"].startswith("attachment")
    assert attached.headers["x-content-type-options"] == "nosniff"  # protective headers kept
    assert attached.content == inline.content

    original = client.get(f"/api/v1/artifacts/{artifact_id}/content", params={"download": "true"})
    assert original.headers["content-disposition"].startswith("attachment")
    assert fixtures.video_static.name in original.headers["content-disposition"]
