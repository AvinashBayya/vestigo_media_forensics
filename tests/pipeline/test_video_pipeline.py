"""The video.v1 pipeline (M3): job flow, media info, and evidence completeness."""

import pytest
from fastapi.testclient import TestClient

from app.core.container import AppServices
from tests.fixtures.make_fixtures import VIDEO_SCENE_CUTS, VIDEO_SCENES_DURATION, FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_runner import records_for


def start_video_analysis(client: TestClient, artifact_id: str, options: dict | None = None) -> dict:
    payload: dict = {"artifact_id": artifact_id}
    if options is not None:
        payload["options"] = options
    response = client.post("/api/v1/analysis/video", json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def analyse_video(client: TestClient, path, options: dict | None = None) -> tuple[str, str]:
    artifact_id = upload_ok(client, path)["artifact_id"]
    return artifact_id, start_video_analysis(client, artifact_id, options)["job_id"]


def video_report(client: TestClient, artifact_id: str) -> dict:
    response = client.get(f"/api/v1/artifacts/{artifact_id}/evidence")
    assert response.status_code == 200, response.text
    return response.json()


def test_video_analysis_runs_the_video_pipeline(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse_video(client, fixtures.video_scenes)

    job = client.get(f"/api/v1/analysis/jobs/{job_id}").json()
    assert job["pipeline"] == "video.v1"
    assert job["status"] == "completed"
    stages = {stage["stage"]: stage["status"] for stage in job["stages"]}
    assert stages["hashes"] == "succeeded"
    assert stages["media_info"] == "succeeded"
    assert stages["metadata"] == "succeeded"

    # Every record carries the full evidence contract (04-EVIDENCE-MODEL.md §5).
    for record in records_for(services, job_id):
        assert record.method and record.tool and record.tool_version
        assert record.source
        assert record.limitations
        assert record.started_at <= record.completed_at
        assert record.review_state == "UNREVIEWED"
        assert record.classification in ("OBSERVED", "DERIVED")

    hashes = next(r for r in records_for(services, job_id) if r.stage == "hashes")
    assert hashes.payload["matches_upload_record"] is True
    assert any("video looks the same" in item for item in hashes.limitations)


def test_media_info_reports_container_and_streams_as_written(
    client: TestClient, services: AppServices, settings, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse_video(client, fixtures.video_scenes)

    record = next(r for r in records_for(services, job_id) if r.stage == "media_info")
    assert record.status == "succeeded"
    assert record.classification == "OBSERVED"
    container = record.payload["container"]
    assert container["duration_seconds"] == pytest.approx(VIDEO_SCENES_DURATION, abs=0.1)
    assert container["stream_count"] == 2
    [video] = record.payload["video_streams"]
    assert (video["codec"], video["width"], video["height"]) == ("h264", 640, 360)
    assert video["frame_rate"] == 25.0
    [audio] = record.payload["audio_streams"]
    assert (audio["codec"], audio["sample_rate"], audio["channels"]) == ("aac", 44100, 1)
    assert "container-reported" in record.method or any("container" in item for item in record.limitations)
    assert any("No audio is decoded" in item for item in record.limitations)

    raw = settings.data_dir / "artifacts" / artifact_id / "derived" / job_id / "media_info.ffprobe.json"
    assert raw.is_file()
    assert b'"codec_name"' in raw.read_bytes()


def test_media_info_reads_rotation_metadata(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_video(client, fixtures.video_rotated)
    [video] = next(r for r in records_for(services, job_id) if r.stage == "media_info").payload[
        "video_streams"
    ]
    assert video["rotation"] in (90, -90)


def test_exiftool_metadata_runs_on_videos_and_can_be_disabled(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_video(client, fixtures.video_scenes)
    record = next(r for r in records_for(services, job_id) if r.stage == "metadata")
    assert record.status == "succeeded"
    assert "QuickTime" in record.payload["other"]

    _, disabled_job = analyse_video(client, fixtures.video_static, {"metadata": False})
    disabled = next(r for r in records_for(services, disabled_job) if r.stage == "metadata")
    assert disabled.status == "skipped"


def test_video_report_sections(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse_video(client, fixtures.video_scenes)

    report = video_report(client, artifact_id)
    assert report["schema_version"] == "1.2"
    media_info = report["media_info"]
    assert media_info["container"]["format_name"].startswith("mov,mp4")
    assert media_info["provenance"]["stage"] == "media_info"
    assert media_info["provenance"]["tool"] == "ffprobe"
    assert media_info["provenance"]["classification"] == "OBSERVED"
    # Image-only sections are null for a video job.
    for section in ("c2pa", "perceptual_hash", "ocr", "duplicates"):
        assert report[section] is None, section
    assert report["hashes"]["sha256"]
    assert report["artifact"]["duration_seconds"] == pytest.approx(9.0, abs=0.1)


def test_image_report_has_no_media_info(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    assert client.post("/api/v1/analysis/image", json={"artifact_id": artifact_id}).status_code == 202
    assert video_report(client, artifact_id)["media_info"] is None


def test_video_analysis_refuses_an_image_and_validates_options(
    client: TestClient, fixtures: FixtureSet
) -> None:
    image_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    error = assert_error(
        client.post("/api/v1/analysis/video", json={"artifact_id": image_id}), 422, "WRONG_MEDIA_TYPE"
    )
    assert "image" in error["message"]

    video_id = upload_ok(client, fixtures.video_static)["artifact_id"]
    assert_error(
        client.post("/api/v1/analysis/video", json={"artifact_id": video_id, "options": {"ocr": True}}),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(
        client.post("/api/v1/analysis/video", json={"artifact_id": "art_" + "0" * 32}),
        404,
        "ARTIFACT_NOT_FOUND",
    )


def test_video_defaults_from_settings_apply_when_options_are_omitted(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    assert (
        client.patch(
            "/api/v1/settings",
            json={
                "default_video_analysis_options": {
                    "metadata": False,
                    "scene_detection": True,
                    "keyframe_ocr": False,
                    "duplicate_search": True,
                }
            },
        ).status_code
        == 200
    )
    _, job_id = analyse_video(client, fixtures.video_static)

    record = next(r for r in records_for(services, job_id) if r.stage == "metadata")
    assert record.status == "skipped"
    assert record.payload["skip_reason"] == "Disabled by the analysis option 'metadata'."


def test_video_jobs_appear_in_history_with_their_options(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse_video(client, fixtures.video_static, {"keyframe_ocr": True})
    [job] = client.get(f"/api/v1/artifacts/{artifact_id}/jobs").json()["jobs"]
    assert job["pipeline"] == "video.v1"
    assert job["options"] == {
        "metadata": True,
        "scene_detection": True,
        "keyframe_ocr": True,
        "duplicate_search": True,
    }
    assert job["problem_count"] == 0


# --- Scene changes (M3 step 5) ------------------------------------------------------------------


def scene_payload(services: AppServices, job_id: str) -> dict:
    record = next(r for r in records_for(services, job_id) if r.stage == "scene_changes")
    assert record.status == "succeeded", record.errors
    return record.payload


def test_scene_changes_finds_both_cuts(
    client: TestClient, services: AppServices, settings, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse_video(client, fixtures.video_scenes)

    payload = scene_payload(services, job_id)
    assert payload["threshold"] == 0.3
    assert payload["count"] == 2
    times = [change["time"] for change in payload["changes"]]
    assert times == pytest.approx(list(VIDEO_SCENE_CUTS), abs=0.2)
    assert all(change["score"] > 0.3 for change in payload["changes"])

    raw = settings.data_dir / "artifacts" / artifact_id / "derived" / job_id / "scene_changes.ffmpeg.txt"
    assert raw.is_file()
    assert b"lavfi.scene_score" in raw.read_bytes()


def test_static_video_has_no_scene_changes(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_video(client, fixtures.video_static)
    payload = scene_payload(services, job_id)
    assert payload["count"] == 0
    assert payload["changes"] == []


def test_scene_detection_can_be_disabled(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_video(client, fixtures.video_static, {"scene_detection": False})
    record = next(r for r in records_for(services, job_id) if r.stage == "scene_changes")
    assert record.status == "skipped"


def test_scene_changes_report_section(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse_video(client, fixtures.video_scenes)
    section = video_report(client, artifact_id)["scene_changes"]
    assert section["count"] == 2
    assert section["provenance"]["tool"] == "ffmpeg"
    assert any("Scene changes are ordinary editing" in item for item in section["provenance"]["limitations"])
