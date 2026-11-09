"""Local AI runtime and status (Pass 1, D24): off by default, telemetry dead, nothing downloaded."""

import os

from fastapi.testclient import TestClient

from app.services import ai
from tests.helpers import assert_error


def status(client: TestClient) -> dict:
    response = client.get("/api/v1/ai/status")
    assert response.status_code == 200, response.text
    return response.json()


def test_vendor_telemetry_is_disabled_in_process(client: TestClient) -> None:
    """The runtime ships telemetry on; Vestigo forces it off before anything can load it."""
    for key, value in ai.TELEMETRY_ENV.items():
        assert os.environ[key] == value
    assert ai.telemetry_disabled() is True

    body = status(client)
    assert body["telemetry_disabled"] is True
    assert body["telemetry_environment"] == dict(ai.TELEMETRY_ENV)
    # No vendor cloud credential is ever read, so platform fine-tuning cannot be reached.
    assert "NEEDLE_API_KEY" not in os.environ


def test_every_capability_is_off_by_default_with_a_clear_reason(client: TestClient) -> None:
    body = status(client)
    assert (body["ai_enabled"], body["transcription_enabled"], body["semantic_search_enabled"]) == (
        False,
        False,
        False,
    )
    assert (body["drafts_available"], body["transcription_available"], body["semantic_search_available"]) == (
        False,
        False,
        False,
    )
    assert "turned off" in body["drafts_unavailable_reason"]
    assert "nothing is downloaded or sent anywhere" in body["drafts_unavailable_reason"]
    assert "Enable it in Settings" in body["transcription_unavailable_reason"]
    assert body["runtime_package"] == "cactus-needle"


def test_status_reports_the_label_and_limitations(client: TestClient) -> None:
    body = status(client)
    assert body["label"] == "AI-generated, unverified - analyst must review."
    text = " ".join(body["limitations"])
    assert "never evidence" in text
    assert "Vestigo never calculates one" in text  # confidence only when the model supplies it
    assert "Nothing is sent anywhere" in text


def test_known_models_carry_licence_and_source(client: TestClient) -> None:
    models = {model["name"]: model for model in status(client)["known_models"]}
    assert set(models) == {"needle2", "needle3", "whistle"}
    for model in models.values():
        assert model["license"] == "Apache-2.0"
        assert model["source_url"].startswith("https://huggingface.co/Cactus-Compute/")
        assert model["runtime"] == "needle"
        assert model["installed"] is False  # nothing is bundled or fetched
        assert model["generation"] in (2, 3)


def test_a_model_can_be_known_without_being_runnable(client: TestClient) -> None:
    """Generation 3 weights are published without an engine, so "installed" and "runnable" differ.

    Reporting one as the other would be a lie in whichever direction the gap happens to run, so the
    status endpoint carries both, and an unrunnable model carries the reason.
    """
    models = {model["name"]: model for model in status(client)["known_models"]}
    for name in ("needle3", "whistle"):
        if not models[name]["runnable"]:
            assert models[name]["unavailable_reason"]


def test_enabling_without_the_runtime_says_what_is_missing(client: TestClient) -> None:
    assert client.patch("/api/v1/settings", json={"ai_enabled": True}).status_code == 200
    body = status(client)
    assert body["ai_enabled"] is True
    if not body["runtime_installed"]:
        # Honest and actionable: the feature is on, the runtime is absent, and the fix is named.
        assert "pip install cactus-needle" in body["drafts_unavailable_reason"]
        assert body["drafts_available"] is False


def test_model_paths_are_validated_as_settings(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/settings", json={"ai_model_path": "/models/needle3.cact", "ai_enabled": False}
    )
    assert response.status_code == 200, response.text
    assert response.json()["editable"]["ai_model_path"] == "/models/needle3.cact"
    # A path that is not a file leaves the model reported as not installed, never half-ready.
    assert all(model["installed"] is False for model in status(client)["known_models"])
    assert_error(
        client.patch("/api/v1/settings", json={"ai_model_path": "x" * 1001}), 422, "VALIDATION_ERROR"
    )


def test_disabled_provider_refuses_every_capability() -> None:
    provider = ai.DisabledProvider()
    for call in (
        lambda: provider.extract("text", ["field"]),
        lambda: provider.transcribe(__import__("pathlib").Path("a.wav")),
        lambda: provider.embed(["text"]),
    ):
        try:
            call()
        except ai.AIUnavailableError as exc:
            assert "Local AI is turned off" in str(exc)
        else:  # pragma: no cover - a silent success would be the bug
            raise AssertionError("the disabled provider must refuse every capability")
    # The reason is read through the documented property, never a private attribute.
    assert ai.unavailable_reason(provider) == ai.DISABLED_REASON


def test_status_reports_that_downloads_are_blocked(client: TestClient) -> None:
    """The backend makes no outbound request, and says so from an enforced switch, not a promise."""
    body = status(client)
    assert body["offline_enforced"] is True
    assert body["offline_environment"] == dict(ai.OFFLINE_ENV)
    assert body["engine_generation"] == ai.DEFAULT_GENERATION
