"""Basic local settings (M2-8)."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.core import migrations
from app.core.clock import utcnow
from app.core.config import Settings
from app.core.container import AppServices
from app.main import create_app
from app.models import AppSetting
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok

DEFAULT_OPTIONS = {
    "metadata": True,
    "c2pa": True,
    "location_clues": True,
    "structural": True,
    "ocr": True,
    "duplicate_search": True,
}
# Keyframe OCR is off by default (decision M3-3).
DEFAULT_VIDEO_OPTIONS = {
    "metadata": True,
    "c2pa": True,
    "location_clues": True,
    "structural": True,
    "scene_detection": True,
    "keyframe_ocr": False,
    "duplicate_search": True,
}
DEFAULT_AUDIO_OPTIONS = {
    "metadata": True,
    "c2pa": True,
    "location_clues": True,
    "structural": True,
    "duplicate_search": True,
}


def test_defaults_and_environment(client: TestClient, settings: Settings) -> None:
    body = client.get("/api/v1/settings").json()

    assert body["editable"] == {
        "default_analysis_options": DEFAULT_OPTIONS,
        "default_video_analysis_options": DEFAULT_VIDEO_OPTIONS,
        "default_audio_analysis_options": DEFAULT_AUDIO_OPTIONS,
        "library_page_size": 25,
        "auto_analyze_after_upload": True,
        "enabled_search_providers": [],
        "enable_external_map_links": False,
        "ai_enabled": False,
        "transcription_enabled": False,
        "semantic_search_enabled": False,
        "ai_model_path": "",
        "transcription_model_path": "",
    }
    assert body["updated_at"] is None
    env = body["environment"]
    assert env["duplicate_threshold"] == settings.phash_max_distance == 10
    assert env["max_upload_bytes"] == settings.max_upload_bytes
    assert env["ocr_languages"] == ["eng"]
    assert env["schema_revision"] == migrations.head_revision()
    assert env["data_dir"] == str(settings.data_dir.resolve())


def test_partial_update_persists_across_restarts(client: TestClient, settings: Settings) -> None:
    response = client.patch("/api/v1/settings", json={"library_page_size": 50})
    assert response.status_code == 200, response.text
    assert response.json()["editable"]["library_page_size"] == 50
    assert response.json()["editable"]["auto_analyze_after_upload"] is True  # untouched
    assert response.json()["updated_at"]

    client.patch(
        "/api/v1/settings",
        json={
            "auto_analyze_after_upload": False,
            "default_analysis_options": {**DEFAULT_OPTIONS, "ocr": False},
        },
    )
    with TestClient(create_app(settings)) as restarted:
        editable = restarted.get("/api/v1/settings").json()["editable"]
    assert editable == {
        "default_analysis_options": {**DEFAULT_OPTIONS, "ocr": False},
        "default_video_analysis_options": DEFAULT_VIDEO_OPTIONS,
        "default_audio_analysis_options": DEFAULT_AUDIO_OPTIONS,
        "library_page_size": 50,
        "auto_analyze_after_upload": False,
        "enabled_search_providers": [],
        "enable_external_map_links": False,
        "ai_enabled": False,
        "transcription_enabled": False,
        "semantic_search_enabled": False,
        "ai_model_path": "",
        "transcription_model_path": "",
    }


@pytest.mark.parametrize(
    "body",
    [
        {"library_page_size": 7},
        {"library_page_size": "lots"},
        {"auto_analyze_after_upload": "sometimes"},
        {"default_analysis_options": {"ocr": True, "face_matching": True}},
        {"theme": "dark"},
    ],
)
def test_invalid_updates_are_rejected(client: TestClient, body: dict) -> None:
    assert_error(client.patch("/api/v1/settings", json=body), 422, "VALIDATION_ERROR")
    assert client.get("/api/v1/settings").json()["updated_at"] is None


@pytest.mark.parametrize("key", ["phash_max_distance", "duplicate_threshold", "max_upload_bytes", "data_dir"])
def test_environment_settings_are_read_only(client: TestClient, key: str) -> None:
    error = assert_error(client.patch("/api/v1/settings", json={key: 0}), 422, "VALIDATION_ERROR")
    message = error["details"]["errors"][0]["message"]
    assert key in message
    assert "set it in the environment (.env)" in message
    assert client.get("/api/v1/settings").json()["environment"]["duplicate_threshold"] == 10


def test_invalid_stored_value_falls_back_to_the_default(client: TestClient, services: AppServices) -> None:
    with services.db.writer() as session, session.begin():
        session.add(AppSetting(key="library_page_size", value=999, updated_at=utcnow()))
    assert client.get("/api/v1/settings").json()["editable"]["library_page_size"] == 25


def test_default_options_apply_when_a_request_has_none(client: TestClient, fixtures: FixtureSet) -> None:
    client.patch("/api/v1/settings", json={"default_analysis_options": {**DEFAULT_OPTIONS, "ocr": False}})
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]

    job_id = client.post("/api/v1/analysis/image", json={"artifact_id": artifact_id}).json()["job_id"]
    status = client.get(f"/api/v1/analysis/jobs/{job_id}").json()
    assert {s["stage"]: s["status"] for s in status["stages"]}["ocr"] == "skipped"

    explicit = client.post(
        "/api/v1/analysis/image", json={"artifact_id": artifact_id, "options": DEFAULT_OPTIONS}
    ).json()["job_id"]
    stages = {
        s["stage"]: s["status"] for s in client.get(f"/api/v1/analysis/jobs/{explicit}").json()["stages"]
    }
    assert stages["ocr"] == "succeeded"


def test_setting_values_are_not_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        client.patch("/api/v1/settings", json={"library_page_size": 100, "auto_analyze_after_upload": False})
    assert "settings.updated" in caplog.text
    assert "count=2" in caplog.text
    assert "100" not in caplog.text
    assert "False" not in caplog.text


def test_external_map_links_are_off_by_default_and_toggleable(client: TestClient) -> None:
    """M6: the only external map affordance is opt-in, and the backend never builds a map URL."""
    assert client.get("/api/v1/settings").json()["editable"]["enable_external_map_links"] is False

    response = client.patch("/api/v1/settings", json={"enable_external_map_links": True})
    assert response.status_code == 200, response.text
    assert response.json()["editable"]["enable_external_map_links"] is True

    assert_error(
        client.patch("/api/v1/settings", json={"enable_external_map_links": "yes please"}),
        422,
        "VALIDATION_ERROR",
    )
