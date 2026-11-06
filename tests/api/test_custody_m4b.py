"""Chain of custody (M4B): recording points, derived-file lineage, and deletion."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.container import AppServices
from app.models import CustodyEvent, DerivedFile
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import upload_ok
from tests.pipeline.test_duplicates import analyse
from tests.pipeline.test_video_pipeline import analyse_video


def events_for(services: AppServices, artifact_id: str) -> list[CustodyEvent]:
    with services.db.reader() as session:
        stmt = (
            select(CustodyEvent)
            .where(CustodyEvent.artifact_id == artifact_id)
            .order_by(CustodyEvent.created_at)
        )
        return list(session.scalars(stmt))


def test_export_records_a_custody_event_with_the_package_hash(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse(client, fixtures.jpeg)
    assert events_for(services, artifact_id) == []  # upload and analysis live in their own tables

    response = client.get(f"/api/v1/artifacts/{artifact_id}/export")
    assert response.status_code == 200

    (event,) = events_for(services, artifact_id)
    assert event.event_type == "exported"
    assert event.detail["job_id"] == job_id
    assert event.detail["package_sha256"] == response.headers["x-vestigo-export-sha256"]
    assert event.detail["original_included"] is False

    client.get(f"/api/v1/artifacts/{artifact_id}/export", params={"include_original": "true"})
    first, second = events_for(services, artifact_id)
    assert first.id == event.id  # append-only: the first event is unchanged
    assert second.detail["original_included"] is True


def test_library_toggle_records_changes_but_never_noops(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    url = f"/api/v1/artifacts/{artifact_id}/duplicate-library"

    assert client.patch(url, json={"included": False}).status_code == 200
    assert client.patch(url, json={"included": False}).status_code == 200  # no-op: nothing recorded
    assert client.patch(url, json={"included": True}).status_code == 200

    excluded, included = events_for(services, artifact_id)
    assert excluded.event_type == "library_changed"
    assert excluded.detail == {"included_before": True, "included_after": False}
    assert included.detail == {"included_before": False, "included_after": True}


def test_preview_creation_is_recorded_once(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.video_ffv1)["artifact_id"]
    info = client.post(f"/api/v1/artifacts/{artifact_id}/preview").json()
    client.post(f"/api/v1/artifacts/{artifact_id}/preview")  # idempotent: returns the existing copy

    (event,) = events_for(services, artifact_id)
    assert event.event_type == "preview_created"
    assert event.detail["sha256"] == info["sha256"]
    assert event.detail["size_bytes"] == info["size_bytes"]


def test_derived_files_record_their_source(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_video(client, fixtures.video_static, {"keyframe_ocr": True})
    with services.db.reader() as session:
        rows = list(session.scalars(select(DerivedFile).where(DerivedFile.job_id == job_id)))

    by_stage: dict[str, list[DerivedFile]] = {}
    for row in rows:
        by_stage.setdefault(row.stage, []).append(row)

    # Every file except the keyframe-OCR output was read straight from the upload, and says so.
    assert {"metadata", "media_info", "keyframes"} <= set(by_stage)
    for stage, stage_rows in by_stage.items():
        if stage == "keyframe_ocr":
            continue
        for row in stage_rows:
            assert (row.source_kind, row.source_derived_file_id) == ("original", None), row.stage

    # Keyframe OCR output was read from a keyframe thumbnail of the same job, and the lineage
    # points at that exact derived file.
    thumbnails = {row.id for row in by_stage["keyframes"]}
    assert by_stage["keyframe_ocr"]
    for row in by_stage["keyframe_ocr"]:
        assert row.source_kind == "derived_file"
        assert row.source_derived_file_id in thumbnails


def test_custody_events_are_deleted_with_the_artifact_and_counted(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse(client, fixtures.jpeg)
    client.patch(f"/api/v1/artifacts/{artifact_id}/duplicate-library", json={"included": False})
    client.get(f"/api/v1/artifacts/{artifact_id}/export")
    assert len(events_for(services, artifact_id)) == 2

    summary = client.delete(f"/api/v1/artifacts/{artifact_id}").json()
    assert summary["custody_events"] == 2
    assert events_for(services, artifact_id) == []
    with services.db.reader() as session:
        assert session.scalars(select(CustodyEvent)).first() is None
