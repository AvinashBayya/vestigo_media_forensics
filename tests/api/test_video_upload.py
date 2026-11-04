"""Video upload and validation (M3 step 3): container sniffing, ffprobe checks, and limits."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import AppServices
from app.main import create_app
from tests.fixtures.make_fixtures import VIDEO_SCENES_DURATION, FixtureSet
from tests.helpers import assert_error, upload, upload_ok


def test_mp4_upload_reports_video_facts(client: TestClient, fixtures: FixtureSet) -> None:
    body = upload_ok(client, fixtures.video_scenes)

    assert body["media_type"] == "video"
    assert body["mime_type"] == "video/mp4"
    assert body["filename"] == "scenes.mp4"

    detail = client.get(f"/api/v1/artifacts/{body['artifact_id']}").json()
    assert (detail["width"], detail["height"]) == (640, 360)
    assert detail["duration_seconds"] == pytest.approx(VIDEO_SCENES_DURATION, abs=0.1)
    assert detail["latest_job"] is None


@pytest.mark.parametrize(
    ("fixture", "mime_type"),
    [
        ("video_mov", "video/quicktime"),
        ("video_webm", "video/webm"),  # VP9 + Opus: the WebM codec profile
        ("video_mkv", "video/x-matroska"),  # H.264 + AAC in an EBML container is Matroska, not WebM
        ("video_rotated", "video/mp4"),
        ("video_no_audio", "video/mp4"),
    ],
)
def test_each_container_is_classified_from_its_bytes(
    client: TestClient, fixtures: FixtureSet, fixture: str, mime_type: str
) -> None:
    body = upload_ok(client, getattr(fixtures, fixture))
    assert body["media_type"] == "video"
    assert body["mime_type"] == mime_type
    stored = client.get(f"/api/v1/artifacts/{body['artifact_id']}/content")
    assert stored.status_code == 200
    assert stored.headers["content-type"] == mime_type


def test_video_original_is_stored_read_only(
    client: TestClient, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.video_scenes)["artifact_id"]
    [original] = list((settings.data_dir / "artifacts" / artifact_id / "original").iterdir())
    assert original.name == f"{artifact_id}.mp4"
    assert original.read_bytes() == fixtures.video_scenes.read_bytes()
    assert (original.stat().st_mode & 0o777) == 0o444


def test_content_endpoint_supports_range_requests_for_video_seeking(
    client: TestClient, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.video_scenes)["artifact_id"]
    response = client.get(f"/api/v1/artifacts/{artifact_id}/content", headers={"Range": "bytes=0-99"})
    assert response.status_code == 206
    assert len(response.content) == 100
    assert response.content[4:8] == b"ftyp"


def test_audio_only_mp4_is_accepted_as_audio(client: TestClient, fixtures: FixtureSet) -> None:
    # Since D19 an MP4-family file without a video stream is a valid audio artifact (M4A).
    body = upload_ok(client, fixtures.audio_only_mp4)
    assert body["media_type"] == "audio"
    assert body["mime_type"] == "audio/mp4"


def test_truncated_video_is_rejected(client: TestClient, fixtures: FixtureSet) -> None:
    assert_error(upload(client, fixtures.truncated_mp4), 422, "INVALID_VIDEO")


def test_html_named_mp4_is_rejected(client: TestClient, fixtures: FixtureSet) -> None:
    assert_error(upload(client, fixtures.html_named_mp4), 415, "UNSUPPORTED_MEDIA_TYPE")


def _client(tmp_path, **overrides) -> TestClient:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", job_mode="inline", **overrides)
    return TestClient(create_app(settings))


def test_duration_limit(tmp_path, fixtures: FixtureSet) -> None:
    with _client(tmp_path, max_video_duration_seconds=5) as client:
        error = assert_error(upload(client, fixtures.video_scenes), 422, "VIDEO_TOO_LONG")
    assert error["details"]["max_duration_seconds"] == 5


def test_resolution_limit(tmp_path, fixtures: FixtureSet) -> None:
    with _client(tmp_path, max_video_pixels=100_000) as client:
        error = assert_error(upload(client, fixtures.video_scenes), 422, "VIDEO_RESOLUTION_TOO_LARGE")
    assert "640x360" in error["message"]


def test_video_size_limit(tmp_path, fixtures: FixtureSet) -> None:
    with _client(tmp_path, max_video_upload_bytes=10_000) as client:
        assert_error(upload(client, fixtures.video_scenes), 413, "FILE_TOO_LARGE")


def test_image_cap_still_applies_when_the_video_cap_is_larger(tmp_path, fixtures: FixtureSet) -> None:
    with _client(tmp_path, max_upload_bytes=1_000) as client:
        assert_error(upload(client, fixtures.jpeg), 413, "FILE_TOO_LARGE")
        assert upload(client, fixtures.video_static).status_code == 201


def test_image_analysis_refuses_a_video(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.video_static)["artifact_id"]
    error = assert_error(
        client.post("/api/v1/analysis/image", json={"artifact_id": artifact_id}),
        422,
        "WRONG_MEDIA_TYPE",
    )
    assert "video" in error["message"]
    assert client.get(f"/api/v1/artifacts/{artifact_id}/jobs").json()["jobs"] == []


def test_videos_appear_in_the_library_with_duration_and_type_filter(
    client: TestClient, fixtures: FixtureSet
) -> None:
    upload_ok(client, fixtures.jpeg)
    video_id = upload_ok(client, fixtures.video_scenes)["artifact_id"]

    listed = client.get("/api/v1/artifacts", params={"mime_type": "video/mp4"}).json()
    assert [item["artifact_id"] for item in listed["items"]] == [video_id]
    assert listed["items"][0]["duration_seconds"] == pytest.approx(9.0, abs=0.1)
    everything = client.get("/api/v1/artifacts").json()
    image_item = next(i for i in everything["items"] if i["artifact_id"] != video_id)
    assert image_item["duration_seconds"] is None


def test_video_limits_are_reported_read_only_in_settings(client: TestClient) -> None:
    body = client.get("/api/v1/settings").json()
    env = body["environment"]
    assert env["max_video_upload_bytes"] == 500 * 1024 * 1024
    assert env["max_video_duration_seconds"] == 900
    assert env["max_video_pixels"] == 8_294_400
    assert env["max_keyframes"] == 40
    assert env["scene_threshold"] == 0.3
    assert env["video_timeout_seconds"] == 600
    error = assert_error(
        client.patch("/api/v1/settings", json={"max_video_duration_seconds": 10}), 422, "VALIDATION_ERROR"
    )
    assert "environment" in str(error["details"])


# --- Additional containers (D19) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "mime_type", "extension"),
    [
        ("video_avi", "video/x-msvideo", "avi"),
        ("video_ts", "video/mp2t", "ts"),
        ("video_wmv", "video/x-ms-wmv", "wmv"),
        ("video_flv", "video/x-flv", "flv"),
        ("video_3gp", "video/3gpp", "3gp"),
    ],
)
def test_additional_containers_are_classified_from_their_bytes(
    client: TestClient, settings: Settings, fixtures: FixtureSet, fixture: str, mime_type: str, extension: str
) -> None:
    body = upload_ok(client, getattr(fixtures, fixture))
    assert body["media_type"] == "video"
    assert body["mime_type"] == mime_type
    artifact_id = body["artifact_id"]
    [original] = list((settings.data_dir / "artifacts" / artifact_id / "original").iterdir())
    assert original.suffix == f".{extension}"


def test_avi_and_ts_run_the_full_video_pipeline(client: TestClient, fixtures: FixtureSet) -> None:
    for fixture in ("video_avi", "video_ts"):
        artifact_id = upload_ok(client, getattr(fixtures, fixture))["artifact_id"]
        assert client.post("/api/v1/analysis/video", json={"artifact_id": artifact_id}).status_code == 202
        report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
        assert report["media_info"]["video_streams"], fixture
        assert report["keyframes"]["extracted"] >= 8, fixture
        assert report["scene_changes"]["count"] == 2, fixture
        if fixture == "video_ts":
            # ExifTool notes a minor advisory on MPEG-TS; it is surfaced honestly, never hidden.
            assert report["job"]["status"] == "completed_with_errors"
            [error] = report["metadata"]["provenance"]["errors"]
            assert error["type"] == "EXIFTOOL_WARNING"
            assert "[minor]" in error["message"]
            assert report["metadata"]["provenance"]["status"] == "partial"
        else:
            assert report["job"]["status"] == "completed", fixture


def test_ts_and_avi_duplicates_match_the_mp4_original(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    from tests.pipeline.test_video_pipeline import analyse_video

    original_id, _ = analyse_video(client, fixtures.video_scenes)
    ts_id, _ = analyse_video(client, fixtures.video_ts)

    report = client.get(f"/api/v1/artifacts/{ts_id}/evidence").json()
    matches = {m["artifact_id"] for m in report["duplicates"]["matches"]}
    assert original_id in matches  # a remux of the same stream matches frame for frame
