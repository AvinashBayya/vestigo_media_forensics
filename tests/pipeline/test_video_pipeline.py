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
    # Image-only sections are null for a video job (duplicates and c2pa are shared by all pipelines).
    for section in ("perceptual_hash", "ocr"):
        assert report[section] is None, section
    assert report["c2pa"] is not None  # validated for videos since Milestone 4
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
                    "c2pa": True,
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
        "c2pa": True,
        "location_clues": True,
        "structural": True,
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


# --- Duplicate search across videos and images (M3 step 9) --------------------------------------


def duplicates_payload(services: AppServices, job_id: str) -> dict:
    record = next(r for r in records_for(services, job_id) if r.stage == "duplicates")
    assert record.status == "succeeded", record.errors
    return record.payload


def test_reencoded_video_copy_is_found_with_frame_pairs(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    original_id, _ = analyse_video(client, fixtures.video_scenes)
    copy_id, copy_job = analyse_video(client, fixtures.video_webm)

    payload = duplicates_payload(services, copy_job)
    assert payload["threshold"] == 10
    [match] = payload["matches"]
    assert match["artifact_id"] == original_id
    assert match["match_type"] in ("near", "visually_identical")
    assert match["matched_frame_count"] >= 6

    def scene_of(timestamp: float) -> int:
        # The fixture's scenes run 0-3 s, 3-6 s, 6-9 s; 0.1 s of tolerance at the cuts.
        if timestamp < VIDEO_SCENE_CUTS[0] - 0.1:
            return 0
        if timestamp < VIDEO_SCENE_CUTS[1] - 0.1:
            return 1
        return 2

    for pair in match["frame_matches"]:
        assert pair["distance"] <= 10
        # Frames within a static scene are interchangeable, so pairs land in the same scene
        # rather than at identical timestamps.
        assert scene_of(pair["query_timestamp"]) == scene_of(pair["matched_timestamp"])

    report = video_report(client, copy_id)
    [reported] = report["duplicates"]["matches"]
    assert reported["filename"] == "scenes.mp4"
    assert reported["media_type"] == "video"
    assert reported["matched_frame_count"] == match["matched_frame_count"]
    assert "keyframe pHashes of every analysed video" in report["duplicates"]["provenance"]["method"]


def test_unrelated_videos_do_not_match(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    analyse_video(client, fixtures.video_scenes)
    _, static_job = analyse_video(client, fixtures.video_static)
    assert duplicates_payload(services, static_job)["matches"] == []


def test_video_uploaded_twice_is_an_exact_file_match(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    first_id, _ = analyse_video(client, fixtures.video_static)
    _, second_job = analyse_video(client, fixtures.video_static)
    [match] = duplicates_payload(services, second_job)["matches"]
    assert (match["artifact_id"], match["match_type"]) == (first_id, "exact_file")
    assert match["frame_matches"] is None


def test_image_analysis_finds_the_video_it_was_taken_from(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    video_id, _ = analyse_video(client, fixtures.video_scenes)
    image_id = upload_ok(client, fixtures.video_frame_jpg)["artifact_id"]
    assert client.post("/api/v1/analysis/image", json={"artifact_id": image_id}).status_code == 202

    report = client.get(f"/api/v1/artifacts/{image_id}/evidence").json()
    matches = {m["artifact_id"]: m for m in report["duplicates"]["matches"]}
    assert video_id in matches
    match = matches[video_id]
    assert match["media_type"] == "video"
    assert match["matched_frame_count"] == 1
    [pair] = match["frame_matches"]
    assert pair["query_seq"] is None  # the query is a whole image
    assert pair["matched_timestamp"] == pytest.approx(0.0, abs=3.1)  # within the first scene
    assert "keyframe pHashes of every analysed video" in report["duplicates"]["provenance"]["method"]


def test_video_analysis_finds_a_matching_image(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    image_id = upload_ok(client, fixtures.video_frame_jpg)["artifact_id"]
    assert client.post("/api/v1/analysis/image", json={"artifact_id": image_id}).status_code == 202
    _, video_job = analyse_video(client, fixtures.video_scenes)

    matches = {m["artifact_id"]: m for m in duplicates_payload(services, video_job)["matches"]}
    assert image_id in matches
    match = matches[image_id]
    assert match["matched_frame_count"] == len(match["frame_matches"]) >= 1
    assert all(pair["matched_seq"] is None for pair in match["frame_matches"])  # a whole image
    # pHash is a coarse-structure measure, so other flat-field scenes with same-position text can
    # also pair within the threshold; the closest pair must be the frame the still was taken from.
    best = min(match["frame_matches"], key=lambda pair: pair["distance"])
    assert best["query_timestamp"] < 3.1  # within scene one
    assert best["distance"] <= 4


def test_excluded_video_is_skipped_by_video_duplicate_search(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    original_id, _ = analyse_video(client, fixtures.video_scenes)
    assert (
        client.patch(
            f"/api/v1/artifacts/{original_id}/duplicate-library", json={"included": False}
        ).status_code
        == 200
    )
    _, copy_job = analyse_video(client, fixtures.video_webm)

    payload = duplicates_payload(services, copy_job)
    assert payload["matches"] == []
    assert payload["excluded_count"] == 1


def test_video_duplicates_can_be_disabled_and_show_in_library_indicators(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    analyse_video(client, fixtures.video_scenes)
    copy_id, _ = analyse_video(client, fixtures.video_webm)
    off_id = upload_ok(client, fixtures.video_static)["artifact_id"]
    start_video_analysis(client, off_id, {"duplicate_search": False})

    listed = {i["artifact_id"]: i for i in client.get("/api/v1/artifacts").json()["items"]}
    assert listed[copy_id]["duplicate_match_count"] == 1
    assert listed[off_id]["duplicate_match_count"] is None
    with_duplicates = client.get("/api/v1/artifacts", params={"has_duplicates": "true"}).json()
    assert [i["artifact_id"] for i in with_duplicates["items"]] == [copy_id]


# --- Deletion and export of video artifacts (M3 step 11) ----------------------------------------


def test_video_deletion_removes_original_derived_files_and_rows(
    client: TestClient, services: AppServices, settings, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse_video(client, fixtures.video_scenes, {"keyframe_ocr": True})
    artifact_dir = settings.data_dir / "artifacts" / artifact_id
    assert any(artifact_dir.glob("derived/*/keyframes.*.jpg"))

    summary = client.delete(f"/api/v1/artifacts/{artifact_id}").json()

    assert summary["original_files"] == 1
    assert summary["derived_files"] > 20  # ffprobe json, scene output, 8 keyframes, OCR TSVs, exiftool
    assert not artifact_dir.exists()
    assert records_for(services, job_id) == []
    with services.db.reader() as session:
        assert session.scalar(select(func.count()).select_from(KeyframeFingerprint)) == 0


def test_video_evidence_package_contains_keyframes_and_raw_tool_output(
    client: TestClient, fixtures: FixtureSet
) -> None:
    import hashlib
    import io
    import json
    import zipfile

    artifact_id, job_id = analyse_video(client, fixtures.video_scenes)
    response = client.get(f"/api/v1/artifacts/{artifact_id}/export")
    assert response.status_code == 200
    package = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(package.namelist())

    assert "derived/media_info.ffprobe.json" in names
    assert "derived/scene_changes.ffmpeg.txt" in names
    keyframes = [name for name in names if name.startswith("derived/keyframes.")]
    assert len(keyframes) == 8
    manifest = json.loads(package.read("manifest.json"))
    assert manifest["job_id"] == job_id
    assert manifest["problems"] == []
    for entry in manifest["files"]:
        assert entry["sha256"] == hashlib.sha256(package.read(entry["path"])).hexdigest()
    report = json.loads(package.read("report.json"))
    assert report["media_info"]["container"]["duration_seconds"] == pytest.approx(9.0, abs=0.1)


# --- Rotated and mirrored duplicate matching (D19) ----------------------------------------------


def test_display_rotated_copy_now_matches_with_the_rotation_recorded(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    original_id, _ = analyse_video(client, fixtures.video_scenes)
    _, rotated_job = analyse_video(client, fixtures.video_rotated)

    payload = duplicates_payload(services, rotated_job)
    [match] = payload["matches"]
    assert match["artifact_id"] == original_id
    assert match["distance"] <= 4
    assert match["matched_frame_count"] >= 6
    for pair in match["frame_matches"]:
        assert (pair["rotation_degrees"], pair["mirrored"]) == (270, False)
    assert payload["threshold"] == 10  # unchanged


def test_mirrored_copy_matches_with_mirrored_recorded(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    original_id, _ = analyse_video(client, fixtures.video_scenes)
    _, mirrored_job = analyse_video(client, fixtures.video_mirrored)

    [match] = duplicates_payload(services, mirrored_job)["matches"]
    assert match["artifact_id"] == original_id
    assert all(pair["mirrored"] for pair in match["frame_matches"])
    assert all(pair["distance"] <= 10 for pair in match["frame_matches"])


def test_upright_matches_still_report_as_upright(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    analyse_video(client, fixtures.video_scenes)
    _, copy_job = analyse_video(client, fixtures.video_webm)
    [match] = duplicates_payload(services, copy_job)["matches"]
    best = min(match["frame_matches"], key=lambda pair: pair["distance"])
    assert (best["rotation_degrees"], best["mirrored"]) == (0, False)


def test_orientation_variants_add_no_false_matches(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    analyse_video(client, fixtures.video_scenes)
    _, static_job = analyse_video(client, fixtures.video_static)
    assert duplicates_payload(services, static_job)["matches"] == []


def test_rotated_image_copy_matches_its_original(
    client: TestClient, services: AppServices, fixtures: FixtureSet, tmp_path
) -> None:
    from PIL import Image

    rotated = tmp_path / "rotated.png"
    mirrored = tmp_path / "mirrored.png"
    with Image.open(fixtures.png) as image:
        image.rotate(90, expand=True).save(rotated)
        image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(mirrored)

    original_id = upload_ok(client, fixtures.png)["artifact_id"]
    assert client.post("/api/v1/analysis/image", json={"artifact_id": original_id}).status_code == 202

    for path, expect_mirrored in ((rotated, False), (mirrored, True)):
        artifact_id = upload_ok(client, path)["artifact_id"]
        assert client.post("/api/v1/analysis/image", json={"artifact_id": artifact_id}).status_code == 202
        report = video_report(client, artifact_id)
        matches = {m["artifact_id"]: m for m in report["duplicates"]["matches"]}
        assert original_id in matches, path.name
        match = matches[original_id]
        [pair] = match["frame_matches"]  # oriented image matches carry the pair detail
        assert pair["mirrored"] is expect_mirrored
        assert pair["distance"] <= 4
        if not expect_mirrored:
            assert pair["rotation_degrees"] in (90, 270)

    # The evidence records why: the method text names the variants.
    method = report["duplicates"]["provenance"]["method"]
    assert "rotated (90/180/270 degrees) and mirrored variants" in method


def test_keyframe_phash_payload_records_orientation_variants(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_video(client, fixtures.video_static)
    record = next(r for r in records_for(services, job_id) if r.stage == "keyframe_phash")
    frame = record.payload["frames"][0]
    assert set(frame["orientations"]) == {
        "rot90",
        "rot180",
        "rot270",
        "mirror",
        "mirror_rot90",
        "mirror_rot180",
        "mirror_rot270",
    }
    with services.db.reader() as session:
        row = session.scalars(select(KeyframeFingerprint)).first()
    assert row.value_hex == frame["value"]  # the index still stores only the canonical hash
