"""Staged local AI model files, and the refusals around them (D27).

Model files are the one third-party binary an analyst puts on this machine on purpose. They are not
evidence: they live beside the evidence store, nothing fetches them, and removing one takes nothing
an analyst recorded with it.
"""

import io

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.container import AppServices
from app.models import DerivedFile
from app.services import ai
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok

MODELS = "/api/v1/ai/models"


def post_model(client: TestClient, name: str, body: bytes = b"pretend weights"):
    return client.post(
        f"{MODELS}/import", files={"file": (name, io.BytesIO(body), "application/octet-stream")}
    )


def test_the_models_directory_starts_empty_and_says_where_it_is(
    client: TestClient, services: AppServices
) -> None:
    body = client.get(MODELS).json()
    assert body["models"] == []
    assert body["models_directory"] == str(services.storage.models_dir)
    assert "never downloads" in body["notice"]
    assert any("does not validate the contents" in limit for limit in body["limitations"])


def test_a_staged_file_is_listed_with_its_measured_digest(client: TestClient) -> None:
    created = post_model(client, "needle2.cact", b"pretend weights")
    assert created.status_code == 201, created.text
    model = created.json()
    assert model["name"] == "needle2.cact"
    assert model["size_bytes"] == len(b"pretend weights")
    assert model["configured_for"] == []

    listed = client.get(MODELS).json()["models"]
    assert [item["name"] for item in listed] == ["needle2.cact"]
    # The digest is measured from the bytes on disk, not taken from the upload.
    import hashlib

    assert listed[0]["sha256"] == hashlib.sha256(b"pretend weights").hexdigest()


def test_a_file_copied_in_by_hand_is_listed_just_the_same(
    client: TestClient, services: AppServices
) -> None:
    """The directory scan is the contract, so staging without the endpoint works identically."""
    (services.storage.models_dir / "dropped.cact").write_bytes(b"by hand")
    assert [item["name"] for item in client.get(MODELS).json()["models"]] == ["dropped.cact"]


def test_only_model_archives_are_accepted(client: TestClient) -> None:
    assert_error(post_model(client, "notes.txt"), 415, "UNSUPPORTED_MEDIA_TYPE")
    assert_error(post_model(client, "../escape.cact"), 422, "VALIDATION_ERROR")
    assert_error(post_model(client, "weird name.cact"), 422, "VALIDATION_ERROR")
    assert_error(post_model(client, "empty.cact", b""), 422, "EMPTY_FILE")
    assert client.get(MODELS).json()["models"] == []


def test_a_staged_model_is_never_silently_replaced(client: TestClient) -> None:
    assert post_model(client, "needle2.cact", b"first").status_code == 201
    assert_error(post_model(client, "needle2.cact", b"second"), 409, "VALIDATION_ERROR")
    listed = client.get(MODELS).json()["models"]
    assert listed[0]["size_bytes"] == len(b"first")


def test_an_oversized_model_is_refused(client: TestClient, services: AppServices) -> None:
    services.settings.max_model_bytes = 8
    assert_error(post_model(client, "big.cact", b"far too many bytes"), 413, "FILE_TOO_LARGE")
    assert client.get(MODELS).json()["models"] == []
    # The rejected upload leaves nothing behind in the scratch directory.
    assert list(services.storage.tmp_dir.iterdir()) == []


def test_deleting_a_model_requires_it_to_be_unselected(client: TestClient, services: AppServices) -> None:
    post_model(client, "needle2.cact")
    path = str(services.storage.models_dir / "needle2.cact")
    assert client.patch("/api/v1/settings", json={"ai_model_path": path}).status_code == 200

    listed = client.get(MODELS).json()["models"]
    assert listed[0]["configured_for"] == ["ai_model_path"]
    assert_error(client.delete(f"{MODELS}/needle2.cact"), 409, "VALIDATION_ERROR")

    assert client.patch("/api/v1/settings", json={"ai_model_path": ""}).status_code == 200
    assert client.delete(f"{MODELS}/needle2.cact").status_code == 204
    assert client.get(MODELS).json()["models"] == []


def test_deletion_refuses_names_that_are_not_staged_models(client: TestClient) -> None:
    assert_error(client.delete(f"{MODELS}/missing.cact"), 404, "NOT_FOUND")
    assert_error(client.delete(f"{MODELS}/notes.txt"), 422, "VALIDATION_ERROR")


def test_staged_models_survive_a_restart(client: TestClient, services: AppServices) -> None:
    """tmp/ and trash/ are cleared on start; models/ must not be, or a restart eats the weights."""
    post_model(client, "needle2.cact")
    services.storage.prepare()
    assert (services.storage.models_dir / "needle2.cact").is_file()
    assert [item["name"] for item in client.get(MODELS).json()["models"]] == ["needle2.cact"]


def test_a_wrong_model_path_reports_unavailable_rather_than_available(client: TestClient) -> None:
    """A typo must not read as "ready". It failed closed before; now it says what is wrong.

    Which reason comes back depends on the machine: an absent runtime is the more fundamental
    problem and is reported first. Either way the capability is unavailable and the reason is
    something the analyst can act on.
    """
    assert client.patch(
        "/api/v1/settings", json={"ai_enabled": True, "ai_model_path": "/models/typo.cact"}
    ).status_code == 200
    status = client.get("/api/v1/ai/status").json()
    assert status["drafts_available"] is False
    reason = status["drafts_unavailable_reason"]
    if status["runtime_installed"]:
        assert "/models/typo.cact" in reason
    else:
        assert ai.RUNTIME_PACKAGE in reason


def test_transcription_refused_while_off_leaves_no_derived_file(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    """A turned-off feature must not write derived evidence on its way to refusing.

    Audio extraction used to run before the refusal, so a disabled transcriber still produced a WAV,
    a DerivedFile row, and a custody event for work that never happened.
    """
    artifact_id = upload_ok(client, fixtures.audio_mp3)["artifact_id"]
    response = client.post(f"/api/v1/ai/artifacts/{artifact_id}/transcripts", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AI_UNAVAILABLE"

    with services.db.reader() as session:
        rows = list(session.scalars(select(DerivedFile).where(DerivedFile.artifact_id == artifact_id)))
    assert [row for row in rows if "transcription" in row.path] == []
    assert not list(services.storage.artifact_dir(artifact_id).glob("derived/*/transcription*"))


def test_status_reports_the_engine_it_would_load(client: TestClient) -> None:
    status = client.get("/api/v1/ai/status").json()
    assert status["engine_generation"] == ai.DEFAULT_GENERATION
    if status["engine_available"]:
        assert status["engine_path"]
        assert status["engine_unavailable_reason"] is None
    else:
        assert status["engine_unavailable_reason"]
