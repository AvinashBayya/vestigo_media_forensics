"""Playable previews (D19): an on-demand viewing copy, never evidence."""

import io
import json
import subprocess
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import AppServices
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok


def create_preview(client: TestClient, artifact_id: str) -> dict:
    response = client.post(f"/api/v1/artifacts/{artifact_id}/preview")
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_is_created_capped_and_playable(
    client: TestClient, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.video_ffv1)["artifact_id"]
    assert client.get(f"/api/v1/artifacts/{artifact_id}").json()["has_playable_preview"] is False

    info = create_preview(client, artifact_id)

    path = settings.data_dir / "artifacts" / artifact_id / "preview" / "preview.mp4"
    assert path.is_file()
    assert (path.stat().st_mode & 0o777) == 0o444
    assert info["size_bytes"] == path.stat().st_size
    assert info["width"] == 320 and info["height"] == 240
    probe = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
            capture_output=True,
            check=True,
        ).stdout
    )
    [video] = [s for s in probe["streams"] if s["codec_type"] == "video"]
    assert video["codec_name"] == "h264"  # re-encoded from FFV1 into a browser-playable codec
    assert client.get(f"/api/v1/artifacts/{artifact_id}").json()["has_playable_preview"] is True

    content = client.get(f"/api/v1/artifacts/{artifact_id}/preview/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "video/mp4"
    partial = client.get(f"/api/v1/artifacts/{artifact_id}/preview/content", headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206


def test_preview_is_idempotent_and_original_is_untouched(
    client: TestClient, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.video_ffv1)["artifact_id"]
    before = (settings.data_dir / "artifacts" / artifact_id / "original").iterdir()
    original = next(before)
    original_bytes = original.read_bytes()

    first = create_preview(client, artifact_id)
    second = create_preview(client, artifact_id)

    assert first["sha256"] == second["sha256"]
    assert original.read_bytes() == original_bytes
    previews = list((settings.data_dir / "artifacts" / artifact_id / "preview").iterdir())
    assert [p.name for p in previews] == ["preview.mp4"]


def test_preview_refuses_non_videos(client: TestClient, fixtures: FixtureSet) -> None:
    image_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    assert_error(client.post(f"/api/v1/artifacts/{image_id}/preview"), 422, "WRONG_MEDIA_TYPE")
    audio_id = upload_ok(client, fixtures.audio_wav)["artifact_id"]
    assert_error(client.post(f"/api/v1/artifacts/{audio_id}/preview"), 422, "WRONG_MEDIA_TYPE")
    assert_error(client.post(f"/api/v1/artifacts/{'art_' + '0' * 32}/preview"), 404, "ARTIFACT_NOT_FOUND")
    video_id = upload_ok(client, fixtures.video_static)["artifact_id"]
    assert_error(client.get(f"/api/v1/artifacts/{video_id}/preview"), 404, "NOT_FOUND")
    assert_error(client.get(f"/api/v1/artifacts/{video_id}/preview/content"), 404, "NOT_FOUND")


def test_failed_transcode_reports_and_leaves_nothing(
    client: TestClient, settings: Settings, fixtures: FixtureSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.tools import ToolError
    from app.services import previews

    artifact_id = upload_ok(client, fixtures.video_static)["artifact_id"]

    def boom(tool, args, *, timeout, cwd=None):
        raise ToolError("ffmpeg did not finish within 600 seconds.")

    monkeypatch.setattr(previews, "run_tool", boom)
    assert_error(client.post(f"/api/v1/artifacts/{artifact_id}/preview"), 500, "PREVIEW_FAILED")
    assert not (settings.data_dir / "artifacts" / artifact_id / "preview").exists()
    assert list((settings.data_dir / "tmp").iterdir()) == []
    assert client.get(f"/api/v1/artifacts/{artifact_id}").json()["has_playable_preview"] is False


def test_preview_is_deleted_with_the_artifact_and_counted(
    client: TestClient, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.video_ffv1)["artifact_id"]
    create_preview(client, artifact_id)

    summary = client.delete(f"/api/v1/artifacts/{artifact_id}").json()
    assert summary["preview_files"] == 1
    assert not (settings.data_dir / "artifacts" / artifact_id).exists()


def test_preview_stays_out_of_the_evidence_package(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    from tests.pipeline.test_video_pipeline import analyse_video

    artifact_id, _ = analyse_video(client, fixtures.video_static)
    create_preview(client, artifact_id)

    response = client.get(f"/api/v1/artifacts/{artifact_id}/export")
    assert response.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert not any("preview" in name for name in names)

    summary = client.get("/api/v1/library/summary").json()
    assert summary["storage"]["preview_bytes"] > 0
