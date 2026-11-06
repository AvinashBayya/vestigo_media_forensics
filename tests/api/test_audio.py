"""Audio artifacts (D19): upload, the audio.v1 pipeline, and honest byte-identical duplicates."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import AppServices
from app.main import create_app
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload, upload_ok
from tests.pipeline.test_runner import records_for


def analyse_audio(client: TestClient, path, options: dict | None = None) -> tuple[str, str]:
    artifact_id = upload_ok(client, path)["artifact_id"]
    payload: dict = {"artifact_id": artifact_id}
    if options is not None:
        payload["options"] = options
    response = client.post("/api/v1/analysis/audio", json=payload)
    assert response.status_code == 202, response.text
    return artifact_id, response.json()["job_id"]


@pytest.mark.parametrize(
    ("fixture", "mime_type", "extension"),
    [
        ("audio_wav", "audio/wav", "wav"),
        ("audio_mp3", "audio/mpeg", "mp3"),
        ("audio_flac", "audio/flac", "flac"),
        ("audio_ogg", "audio/ogg", "ogg"),
        ("audio_m4a", "audio/mp4", "m4a"),
    ],
)
def test_audio_formats_are_classified_from_their_bytes(
    client: TestClient, settings: Settings, fixtures: FixtureSet, fixture: str, mime_type: str, extension: str
) -> None:
    body = upload_ok(client, getattr(fixtures, fixture))
    assert body["media_type"] == "audio"
    assert body["mime_type"] == mime_type
    detail = client.get(f"/api/v1/artifacts/{body['artifact_id']}").json()
    assert detail["duration_seconds"] == pytest.approx(2.0, abs=0.2)
    assert detail["width"] is None and detail["height"] is None
    [original] = list((settings.data_dir / "artifacts" / body["artifact_id"] / "original").iterdir())
    assert original.suffix == f".{extension}"
    assert (original.stat().st_mode & 0o777) == 0o444


def test_audio_pipeline_runs_header_level_stages_only(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analyse_audio(client, fixtures.audio_mp3)

    job = client.get(f"/api/v1/analysis/jobs/{job_id}").json()
    assert job["pipeline"] == "audio.v1"
    assert job["status"] == "completed"
    assert [stage["stage"] for stage in job["stages"]] == [
        "hashes",
        "media_info",
        "metadata",
        "c2pa",
        "duplicates",
    ]

    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    assert report["hashes"]["sha256"]
    media_info = report["media_info"]
    assert media_info["video_streams"] == []
    [audio] = media_info["audio_streams"]
    assert audio["codec"] == "mp3"
    assert audio["sample_rate"] == 44100
    assert media_info["container"]["duration_seconds"] == pytest.approx(2.0, abs=0.2)
    assert any("No audio is decoded" in item for item in media_info["provenance"]["limitations"])
    # ID3 title written by the fixture surfaces through ExifTool.
    assert any(
        "Vestigo tone" in str(groups) for groups in report["metadata"]["other"].values()
    ) or "Vestigo tone" in str(report["metadata"])
    # No visual sections for audio.
    for section in ("keyframes", "scene_changes", "keyframe_phash", "keyframe_ocr", "perceptual_hash"):
        assert report[section] is None, section

    for record in records_for(services, job_id):
        assert record.method and record.tool and record.tool_version
        assert record.limitations
        assert record.review_state == "UNREVIEWED"


def test_audio_duplicates_are_byte_identical_only_and_say_so(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    wav_id, _ = analyse_audio(client, fixtures.audio_wav)
    # The same recording re-encoded: honestly NOT matched (no content-based audio comparison).
    _, mp3_job = analyse_audio(client, fixtures.audio_mp3)
    mp3_dup = next(r for r in records_for(services, mp3_job) if r.stage == "duplicates")
    assert mp3_dup.payload["matches"] == []
    assert any("will NOT match" in item for item in mp3_dup.limitations)
    assert "fingerprinting" in mp3_dup.method

    # A byte-identical copy matches.
    copy_id, copy_job = analyse_audio(client, fixtures.audio_wav)
    copy_dup = next(r for r in records_for(services, copy_job) if r.stage == "duplicates")
    [match] = copy_dup.payload["matches"]
    assert (match["artifact_id"], match["match_type"]) == (wav_id, "exact_file")

    report = client.get(f"/api/v1/artifacts/{copy_id}/evidence").json()
    [reported] = report["duplicates"]["matches"]
    assert reported["media_type"] == "audio"
    assert reported["filename"] == "tone.wav"


def test_audio_duplicates_respect_exclusion(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    wav_id, _ = analyse_audio(client, fixtures.audio_wav)
    client.patch(f"/api/v1/artifacts/{wav_id}/duplicate-library", json={"included": False})
    _, copy_job = analyse_audio(client, fixtures.audio_wav)
    record = next(r for r in records_for(services, copy_job) if r.stage == "duplicates")
    assert record.payload["matches"] == []
    assert record.payload["excluded_count"] == 1


def test_audio_endpoint_guards_and_options(client: TestClient, fixtures: FixtureSet) -> None:
    video_id = upload_ok(client, fixtures.video_static)["artifact_id"]
    error = assert_error(
        client.post("/api/v1/analysis/audio", json={"artifact_id": video_id}), 422, "WRONG_MEDIA_TYPE"
    )
    assert "POST /analysis/video" in error["message"]

    audio_id = upload_ok(client, fixtures.audio_wav)["artifact_id"]
    assert_error(
        client.post("/api/v1/analysis/video", json={"artifact_id": audio_id}), 422, "WRONG_MEDIA_TYPE"
    )
    assert_error(
        client.post("/api/v1/analysis/image", json={"artifact_id": audio_id}), 422, "WRONG_MEDIA_TYPE"
    )
    assert_error(
        client.post(
            "/api/v1/analysis/audio", json={"artifact_id": audio_id, "options": {"scene_detection": True}}
        ),
        422,
        "VALIDATION_ERROR",
    )


def test_audio_metadata_can_be_disabled_via_saved_defaults(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    assert (
        client.patch(
            "/api/v1/settings",
            json={
                "default_audio_analysis_options": {"metadata": False, "c2pa": True, "duplicate_search": True}
            },
        ).status_code
        == 200
    )
    _, job_id = analyse_audio(client, fixtures.audio_flac)
    record = next(r for r in records_for(services, job_id) if r.stage == "metadata")
    assert record.status == "skipped"


def test_audio_limits(tmp_path, fixtures: FixtureSet) -> None:
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "data", job_mode="inline", max_audio_duration_seconds=1
    )
    with TestClient(create_app(settings)) as client:
        error = assert_error(upload(client, fixtures.audio_wav), 422, "AUDIO_TOO_LONG")
        assert error["details"]["max_duration_seconds"] == 1
    small = Settings(
        _env_file=None, data_dir=tmp_path / "data2", job_mode="inline", max_audio_upload_bytes=1000
    )
    with TestClient(create_app(small)) as client:
        assert_error(upload(client, fixtures.audio_wav), 413, "FILE_TOO_LARGE")


def test_audio_in_library_filters_and_deletion(
    client: TestClient, settings: Settings, fixtures: FixtureSet
) -> None:
    audio_id, _ = analyse_audio(client, fixtures.audio_ogg)
    upload_ok(client, fixtures.jpeg)

    listed = client.get("/api/v1/artifacts", params={"mime_type": "audio/ogg"}).json()
    assert [item["artifact_id"] for item in listed["items"]] == [audio_id]
    assert listed["items"][0]["duration_seconds"] == pytest.approx(2.0, abs=0.2)

    summary = client.delete(f"/api/v1/artifacts/{audio_id}").json()
    assert summary["original_files"] == 1
    assert not (settings.data_dir / "artifacts" / audio_id).exists()
