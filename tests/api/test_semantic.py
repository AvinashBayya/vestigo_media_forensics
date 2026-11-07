"""Local semantic search and retrieval (Pass 1, D24): own material only, answers never evidence."""

import json

from fastapi.testclient import TestClient

from app.services import ai
from tests.api.test_custody_m4b import events_for
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_duplicates import analyse


def enable(client: TestClient) -> None:
    assert client.patch("/api/v1/settings", json={"semantic_search_enabled": True}).status_code == 200


def test_search_is_refused_until_enabled(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    for response in (
        client.get("/api/v1/ai/search", params={"q": "anything"}),
        client.post(f"/api/v1/ai/artifacts/{artifact_id}/index"),
        client.post("/api/v1/ai/answer", json={"question": "where?"}),
    ):
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "AI_UNAVAILABLE"
        assert "turned off" in response.json()["error"]["message"]


def test_indexing_covers_the_analysts_own_material(client: TestClient, fixtures: FixtureSet) -> None:
    enable(client)
    artifact_id, _ = analyse(client, fixtures.ocr_text)
    client.patch(
        f"/api/v1/artifacts/{artifact_id}/review",
        json={"state": "IN_REVIEW", "analyst_notes": "Harbour photo from the Testville case file."},
    )
    client.post(
        f"/api/v1/artifacts/{artifact_id}/location-candidates",
        json={
            "description": "Near the old harbour",
            "basis": "A legible street sign in the image",
            "analyst_assessment": "possible",
        },
    )

    result = client.post(f"/api/v1/ai/artifacts/{artifact_id}/index")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["chunks"] > 0
    assert body["model"] == "vestigo-local-hash"
    # Notes, OCR text, metadata, and the analyst's own candidate are all indexed.
    assert {"analyst_notes", "ocr_text", "metadata", "location_candidate"} <= set(body["sources"])


def test_search_finds_the_analysts_notes_and_never_leaves_the_machine(
    client: TestClient, fixtures: FixtureSet
) -> None:
    enable(client)
    first, _ = analyse(client, fixtures.jpeg)
    second, _ = analyse(client, fixtures.png)
    client.patch(
        f"/api/v1/artifacts/{first}/review",
        json={"state": "IN_REVIEW", "analyst_notes": "Suspected harbour scene, Testville waterfront."},
    )
    client.patch(
        f"/api/v1/artifacts/{second}/review",
        json={"state": "IN_REVIEW", "analyst_notes": "Unrelated indoor studio shot."},
    )
    client.post(f"/api/v1/ai/artifacts/{first}/index")
    client.post(f"/api/v1/ai/artifacts/{second}/index")

    hits = client.get("/api/v1/ai/search", params={"q": "harbour waterfront"}).json()
    assert hits["model"] == "vestigo-local-hash"
    assert hits["hits"], hits
    top = hits["hits"][0]
    assert top["artifact_id"] == first
    assert top["source_kind"] == "analyst_notes"
    assert "Testville" in top["text"]
    assert 0.0 < top["score"] <= 1.0


def test_answers_always_carry_sources_and_are_never_stored(client: TestClient, fixtures: FixtureSet) -> None:
    enable(client)
    artifact_id, _ = analyse(client, fixtures.jpeg)
    client.patch(
        f"/api/v1/artifacts/{artifact_id}/review",
        json={"state": "IN_REVIEW", "analyst_notes": "The camera was a VestigoTestCam near Testville."},
    )
    client.post(f"/api/v1/ai/artifacts/{artifact_id}/index")

    response = client.post("/api/v1/ai/answer", json={"question": "which camera near Testville?"})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["sources"], body
    assert body["sources"][0]["artifact_id"] == artifact_id
    # With no local generator installed, Vestigo returns the material instead of inventing prose,
    # and the notice says why rather than leaving an empty answer unexplained.
    assert body["answer"] is None
    assert any(
        phrase in body["notice"]
        for phrase in ("No local text-generation model is available", "Local AI is turned off")
    ), body["notice"]
    assert body["label"] == ai.AI_LABEL

    # Nothing about the answer is persisted anywhere, and it is not in the evidence report.
    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    assert "answer" not in json.dumps(report)
    again = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    report.pop("created_at"), again.pop("created_at")  # the report's own build time
    assert again == report  # asking a question changed no stored evidence


def test_answer_can_be_scoped_to_chosen_artifacts(client: TestClient, fixtures: FixtureSet) -> None:
    enable(client)
    first, _ = analyse(client, fixtures.jpeg)
    second, _ = analyse(client, fixtures.png)
    for artifact_id, note in ((first, "harbour crane detail"), (second, "harbour ferry detail")):
        client.patch(
            f"/api/v1/artifacts/{artifact_id}/review", json={"state": "IN_REVIEW", "analyst_notes": note}
        )
        client.post(f"/api/v1/ai/artifacts/{artifact_id}/index")

    scoped = client.post("/api/v1/ai/answer", json={"question": "harbour", "artifact_ids": [second]}).json()
    assert {hit["artifact_id"] for hit in scoped["sources"]} == {second}


def test_index_is_rebuildable_deletable_and_custody_trailed(
    client: TestClient, services, fixtures: FixtureSet
) -> None:
    enable(client)
    artifact_id, _ = analyse(client, fixtures.jpeg)
    client.patch(
        f"/api/v1/artifacts/{artifact_id}/review",
        json={"state": "IN_REVIEW", "analyst_notes": "A note worth indexing."},
    )

    first = client.post(f"/api/v1/ai/artifacts/{artifact_id}/index").json()
    again = client.post(f"/api/v1/ai/artifacts/{artifact_id}/index").json()
    assert again["chunks"] == first["chunks"]  # rebuilt, not duplicated

    cleared = client.delete(f"/api/v1/ai/artifacts/{artifact_id}/index").json()
    assert cleared["chunks"] == 0
    assert client.get("/api/v1/ai/search", params={"q": "indexing"}).json()["hits"] == []

    events = [event.event_type for event in events_for(services, artifact_id)]
    assert events == ["embeddings_indexed", "embeddings_indexed", "embeddings_cleared"]

    # Rebuilt once more, the index is counted and removed with the artifact.
    client.post(f"/api/v1/ai/artifacts/{artifact_id}/index")
    summary = client.delete(f"/api/v1/artifacts/{artifact_id}").json()
    assert summary["embedding_chunks"] > 0


def test_search_validation(client: TestClient) -> None:
    enable(client)
    assert client.get("/api/v1/ai/search", params={"q": "x", "limit": 1}).status_code == 200
    assert_error(client.post("/api/v1/ai/answer", json={"question": ""}), 422, "VALIDATION_ERROR")
    assert_error(
        client.post("/api/v1/ai/answer", json={"question": "x", "extra": 1}), 422, "VALIDATION_ERROR"
    )
    missing = f"/api/v1/ai/artifacts/{'art_' + '0' * 32}/index"
    assert_error(client.post(missing), 404, "ARTIFACT_NOT_FOUND")
