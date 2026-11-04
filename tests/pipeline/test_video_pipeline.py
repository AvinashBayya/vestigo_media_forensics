"""The video.v1 pipeline (M3): job flow, media info, and evidence completeness."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.container import AppServices
from app.models import KeyframeFingerprint
from app.services.phash import hamming_distance
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

    # Every record carries the full evidence contract (04-EVIDENCE-MODEL.md §5). tool_version is
    # null only when the tool was never invoked (a skipped stage).
    for record in records_for(services, job_id):
        assert record.method and record.tool
        assert record.tool_version or record.status == "skipped"
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


# --- Keyframes (M3 step 6) ----------------------------------------------------------------------


def keyframes_payload(services: AppServices, job_id: str) -> dict:
    record = next(r for r in records_for(services, job_id) if r.stage == "keyframes")
    assert record.status in ("succeeded", "partial"), record.errors
    return record.payload


def test_keyframes_follow_the_selection_policy(
    client: TestClient, services: AppServices, settings, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse_video(client, fixtures.video_scenes)

    payload = keyframes_payload(services, job_id)
    assert payload["requested"] == payload["extracted"] == 8
    frames = payload["frames"]
    assert [frame["seq"] for frame in frames] == list(range(1, 9))
    reasons = [frame["reason"] for frame in frames]
    assert reasons[0] == "first_frame"
    assert reasons.count("scene_change") == 2
    assert reasons.count("uniform_sample") == 5
    scene_times = [frame["timestamp"] for frame in frames if frame["reason"] == "scene_change"]
    assert scene_times == pytest.approx(list(VIDEO_SCENE_CUTS), abs=0.2)
    assert all(frame["width"] == 640 and frame["height"] == 360 for frame in frames)

    derived_dir = settings.data_dir / "artifacts" / artifact_id / "derived" / job_id
    stored = sorted(derived_dir.glob("keyframes.*.jpg"))
    assert len(stored) == 8
    assert all(path.read_bytes().startswith(b"\xff\xd8\xff") for path in stored)
    assert payload["policy"]["max_keyframes"] == 40


def test_keyframe_cap_keeps_the_best_scene_changes(tmp_path, fixtures: FixtureSet) -> None:
    from app.core.config import Settings
    from app.main import create_app

    settings = Settings(_env_file=None, data_dir=tmp_path / "data", job_mode="inline", max_keyframes=3)
    app = create_app(settings)
    with TestClient(app) as client:
        artifact_id = upload_ok(client, fixtures.video_scenes)["artifact_id"]
        job_id = start_video_analysis(client, artifact_id)["job_id"]
        payload = keyframes_payload(app.state.services, job_id)

    assert payload["extracted"] == 3
    reasons = [frame["reason"] for frame in payload["frames"]]
    assert reasons[0] == "first_frame"
    assert reasons[1:] == ["scene_change", "scene_change"]


def test_rotated_video_keyframes_are_upright(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_video(client, fixtures.video_rotated)
    frames = keyframes_payload(services, job_id)["frames"]
    assert all(frame["width"] == 360 and frame["height"] == 640 for frame in frames)


def test_failed_extraction_is_a_warning_not_a_silent_drop(
    client: TestClient, services: AppServices, fixtures: FixtureSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.pipeline import video_pipeline
    from app.services.keyframes import extract_keyframe as real_extract

    def flaky(tool, video, timestamp, target, timeout):
        if timestamp > 5.0:
            return False
        return real_extract(tool, video, timestamp, target, timeout)

    monkeypatch.setattr(video_pipeline, "extract_keyframe", flaky)
    _, job_id = analyse_video(client, fixtures.video_scenes)

    record = next(r for r in records_for(services, job_id) if r.stage == "keyframes")
    assert record.status == "partial"
    assert all(error["type"] == "KEYFRAME_EXTRACTION_FAILED" for error in record.errors)
    assert record.payload["extracted"] == record.payload["requested"] - len(record.errors)
    assert all(frame["timestamp"] <= 5.0 for frame in record.payload["frames"])


def test_keyframe_thumbnails_are_served_only_for_their_artifact(
    client: TestClient, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse_video(client, fixtures.video_static)
    other_id = upload_ok(client, fixtures.jpeg)["artifact_id"]

    report = video_report(client, artifact_id)
    frame = report["keyframes"]["frames"][0]
    url = f"/api/v1/artifacts/{artifact_id}/derived/{frame['derived_file_id']}/content"
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.startswith(b"\xff\xd8\xff")

    wrong_owner = f"/api/v1/artifacts/{other_id}/derived/{frame['derived_file_id']}/content"
    assert_error(client.get(wrong_owner), 404, "NOT_FOUND")
    assert_error(
        client.get(f"/api/v1/artifacts/{artifact_id}/derived/df_{'0' * 32}/content"), 404, "NOT_FOUND"
    )
    assert_error(client.get(f"/api/v1/artifacts/{artifact_id}/derived/not-an-id/content"), 404, "NOT_FOUND")


def test_keyframes_report_section(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse_video(client, fixtures.video_scenes)
    section = video_report(client, artifact_id)["keyframes"]
    assert section["extracted"] == 8
    assert section["provenance"]["stage"] == "keyframes"
    assert all(frame["derived_file_id"].startswith("df_") for frame in section["frames"])
    assert any("bounded sample" in item for item in section["provenance"]["limitations"])


# --- Keyframe perceptual hashes (M3 step 7) -----------------------------------------------------


def test_keyframe_hashes_are_recorded_and_indexed(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse_video(client, fixtures.video_scenes)

    record = next(r for r in records_for(services, job_id) if r.stage == "keyframe_phash")
    assert record.status == "succeeded"
    payload = record.payload
    assert payload["count"] == 8
    assert all(re.fullmatch(r"[0-9a-f]{16}", frame["value"]) for frame in payload["frames"])

    with services.db.reader() as session:
        rows = session.scalars(
            select(KeyframeFingerprint).where(KeyframeFingerprint.artifact_id == artifact_id)
        ).all()
    assert len(rows) == 8
    by_seq = {row.frame_seq: row for row in rows}
    for frame in payload["frames"]:
        row = by_seq[frame["seq"]]
        assert row.value_hex == frame["value"]
        assert row.timestamp_seconds == frame["timestamp"]
        assert row.evidence_id == record.id
        assert row.derived_file_id == frame["derived_file_id"]

    section = video_report(client, artifact_id)["keyframe_phash"]
    assert section["bits"] == 64
    assert section["count"] == 8


def test_keyframe_index_is_replaced_on_reanalysis_and_deleted_with_the_artifact(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse_video(client, fixtures.video_static)

    def index_rows():
        with services.db.reader() as session:
            return session.scalars(
                select(KeyframeFingerprint).where(KeyframeFingerprint.artifact_id == artifact_id)
            ).all()

    first_evidence_ids = {row.evidence_id for row in index_rows()}
    start_video_analysis(client, artifact_id)
    rows = index_rows()
    assert len(rows) == 8
    assert {row.evidence_id for row in rows}.isdisjoint(first_evidence_ids)  # replaced, not appended

    assert client.delete(f"/api/v1/artifacts/{artifact_id}").status_code == 200
    with services.db.reader() as session:
        remaining = session.scalar(select(func.count()).select_from(KeyframeFingerprint))
    assert remaining == 0


def test_reencoded_copy_has_matching_keyframe_hashes(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    # The measured basis for video duplicate search: a half-resolution VP9 re-encode of the same
    # video hashes within the existing threshold, frame for frame.
    _, original_job = analyse_video(client, fixtures.video_scenes)
    _, copy_job = analyse_video(client, fixtures.video_webm)

    def hashes(job_id: str) -> dict[int, str]:
        record = next(r for r in records_for(services, job_id) if r.stage == "keyframe_phash")
        return {frame["seq"]: frame["value"] for frame in record.payload["frames"]}

    original, copy = hashes(original_job), hashes(copy_job)
    distances = [hamming_distance(original[seq], copy[seq]) for seq in sorted(set(original) & set(copy))]
    assert distances, "no comparable keyframes"
    assert max(distances) <= 10


# --- Keyframe OCR (M3 step 8) -------------------------------------------------------------------


def test_keyframe_ocr_is_off_by_default(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_video(client, fixtures.video_static)
    record = next(r for r in records_for(services, job_id) if r.stage == "keyframe_ocr")
    assert record.status == "skipped"
    assert record.payload["skip_reason"] == "Disabled by the analysis option 'keyframe_ocr'."


def test_keyframe_ocr_reads_scene_text_when_enabled(
    client: TestClient, services: AppServices, settings, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse_video(client, fixtures.video_scenes, {"keyframe_ocr": True})

    record = next(r for r in records_for(services, job_id) if r.stage == "keyframe_ocr")
    assert record.status == "succeeded", record.errors
    payload = record.payload
    assert payload["frame_limit"] == 10
    assert payload["analyzed"] == 8  # all 8 keyframes fit within the limit
    texts = {frame["seq"]: frame["text"].upper() for frame in payload["frames"]}
    assert "SCENE ONE" in texts[1]
    assert any("SCENE THREE" in text for text in texts.values())
    first = payload["frames"][0]
    assert first["confidence"] is not None and first["confidence"] > 0.5
    assert first["selected"]["variant"] in ("grayscale", "threshold")
    assert [step["step"] for step in first["preprocessing"]][:2] == ["first_frame", "exif_orientation"]
    assert [candidate["variant"] for candidate in first["candidates"]] == ["grayscale", "threshold"]

    derived_dir = settings.data_dir / "artifacts" / artifact_id / "derived" / job_id
    tsvs = sorted(derived_dir.glob("keyframe_ocr.*.tsv"))
    assert len(tsvs) == 16  # two passes per analysed frame
    assert tsvs[0].read_bytes().startswith(b"level\t")

    section = video_report(client, artifact_id)["keyframe_ocr"]
    assert section["analyzed"] == 8
    assert any("provisional" in item for item in section["provenance"]["limitations"])
    assert any("bounded subset" in item for item in section["provenance"]["limitations"])


def test_keyframe_ocr_frame_failure_is_recorded_not_hidden(
    client: TestClient, services: AppServices, fixtures: FixtureSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.tools import ToolError
    from app.pipeline import video_pipeline
    from app.services.ocr import run_ocr as real_run_ocr

    calls = {"n": 0}

    def flaky(tool, source, scratch_dir, timeout):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ToolError("Tesseract exited with code 1 (boom).")
        return real_run_ocr(tool, source, scratch_dir, timeout)

    monkeypatch.setattr(video_pipeline, "run_ocr", flaky)
    _, job_id = analyse_video(client, fixtures.video_static, {"keyframe_ocr": True})

    record = next(r for r in records_for(services, job_id) if r.stage == "keyframe_ocr")
    assert record.status == "partial"
    assert [error["type"] for error in record.errors] == ["OCR_FRAME_FAILED"]
    assert record.payload["analyzed"] == 7
