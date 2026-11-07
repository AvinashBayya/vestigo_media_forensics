"""AI drafts and transcripts (Pass 1, D24): never evidence, always labelled, custody-trailed."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.core.container import AppServices
from app.services import ai
from app.services.ai.protocols import (
    ExtractedField,
    ExtractionResult,
    TranscriptionResult,
    TranscriptSegment,
)
from tests.api.test_custody_m4b import events_for
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_duplicates import analyse

FAKE_MODEL = ai.ModelInfo(
    name="needle3",
    version="3",
    quantization="2-bit",
    source_url="https://huggingface.co/Cactus-Compute/needle3",
    license="Apache-2.0",
    runtime="needle",
    local_path="/models/needle3.cact",
)


class FakeExtractor:
    """Stands in for the local model: no runtime, no weights, no network."""

    def __init__(self, fields: list[ExtractedField] | None = None) -> None:
        self.fields = (
            fields
            if fields is not None
            else [
                ExtractedField(name="city", value="Testville", confidence=0.72),
                ExtractedField(name="date", value="2026-01-15"),
            ]
        )
        self.seen: list[str] = []

    def extract(self, text: str, fields: list[str]) -> ExtractionResult:
        self.seen.append(text)
        return ExtractionResult(
            fields=[field for field in self.fields if field.name in fields],
            model=FAKE_MODEL,
            reasoning="Matched the city tag and the capture date.",
        )


class FakeTranscriber:
    def transcribe(self, audio_path, language=None) -> TranscriptionResult:  # noqa: ANN001
        return TranscriptionResult(
            segments=[
                TranscriptSegment(
                    0.0,
                    1.5,
                    "testing one two",
                    [{"word": "testing", "start": 0.0, "end": 0.4, "probability": 0.91}],
                ),
                TranscriptSegment(1.5, 2.4, "three"),
            ],
            text="testing one two three",
            language=language or "en",
            model=ai.ModelInfo(
                "whistle",
                "1",
                None,
                "https://huggingface.co/Cactus-Compute/whistle",
                "Apache-2.0",
                "needle",
            ),
            duration_seconds=2.4,
        )


@pytest.fixture
def fake_ai(monkeypatch) -> FakeExtractor:
    extractor = FakeExtractor()
    monkeypatch.setattr(ai, "resolve_extractor", lambda **_: extractor)
    monkeypatch.setattr("app.services.ai_drafts.ai.resolve_extractor", lambda **_: extractor)
    monkeypatch.setattr("app.services.transcripts.ai.resolve_transcriber", lambda **_: FakeTranscriber())
    return extractor


def test_draft_generation_is_refused_while_ai_is_off(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    response = client.post(
        f"/api/v1/ai/artifacts/{artifact_id}/drafts",
        json={"source_kind": "metadata", "fields": ["city"]},
    )
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "AI_UNAVAILABLE"
    assert "turned off" in body["message"]


def test_draft_records_model_provenance_and_model_confidence(
    client: TestClient, services: AppServices, fixtures: FixtureSet, fake_ai: FakeExtractor
) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    response = client.post(
        f"/api/v1/ai/artifacts/{artifact_id}/drafts",
        json={"source_kind": "metadata", "fields": ["city", "date"]},
    )
    assert response.status_code == 201, response.text
    draft = response.json()

    assert draft["draft_id"].startswith("draft_")
    assert draft["source_kind"] == "metadata"
    assert draft["source_evidence_id"].startswith("ev_")  # lineage to the record it read
    assert draft["model"]["license"] == "Apache-2.0"
    assert draft["model"]["source_url"].endswith("needle3")
    assert draft["model"]["quantization"] == "2-bit"
    fields = {field["name"]: field for field in draft["fields"]}
    assert fields["city"]["value"] == "Testville"
    assert fields["city"]["confidence"] == 0.72  # the model's own figure
    assert fields["date"]["confidence"] is None  # never invented when the model gives none
    assert all(field["status"] == "proposed" for field in fields.values())
    # The model actually read the held metadata.
    assert "Testville" in fake_ai.seen[0]

    listed = client.get(f"/api/v1/ai/artifacts/{artifact_id}/drafts").json()
    assert listed["label"] == "AI-generated, unverified - analyst must review."
    assert "not evidence" in listed["notice"]

    (event,) = events_for(services, artifact_id)
    assert event.event_type == "ai_draft_generated"
    assert event.detail["field_names"] == ["city", "date"]
    assert "Testville" not in json.dumps(event.detail)  # no content in the custody trail


def test_fields_are_accepted_edited_or_rejected_one_at_a_time(
    client: TestClient, services: AppServices, fixtures: FixtureSet, fake_ai: FakeExtractor
) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    draft = client.post(
        f"/api/v1/ai/artifacts/{artifact_id}/drafts",
        json={"source_kind": "metadata", "fields": ["city", "date"]},
    ).json()
    url = f"/api/v1/ai/artifacts/{artifact_id}/drafts/{draft['draft_id']}"

    accepted = client.patch(url, json={"field": "city", "action": "accepted"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "proposed"  # one field still undecided

    edited = client.patch(url, json={"field": "date", "action": "edited", "value": "15 January 2026"})
    assert edited.status_code == 200
    fields = {field["name"]: field for field in edited.json()["fields"]}
    assert fields["date"]["edited_value"] == "15 January 2026"
    assert fields["date"]["value"] == "2026-01-15"  # the model's value is kept beside the edit
    assert edited.json()["status"] == "reviewed"

    # An edit needs a value; the other actions must not carry one.
    assert_error(client.patch(url, json={"field": "city", "action": "edited"}), 422, "VALIDATION_ERROR")
    assert_error(
        client.patch(url, json={"field": "city", "action": "rejected", "value": "x"}),
        422,
        "VALIDATION_ERROR",
    )
    assert_error(client.patch(url, json={"field": "nope", "action": "accepted"}), 404, "NOT_FOUND")

    events = [(event.event_type, event.detail.get("action")) for event in events_for(services, artifact_id)]
    assert events == [
        ("ai_draft_generated", None),
        ("ai_draft_field_reviewed", "accepted"),
        ("ai_draft_field_reviewed", "edited"),
    ]


def test_drafts_never_touch_evidence_or_metadata(
    client: TestClient, fixtures: FixtureSet, fake_ai: FakeExtractor
) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    before = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()

    draft = client.post(
        f"/api/v1/ai/artifacts/{artifact_id}/drafts",
        json={"source_kind": "metadata", "fields": ["city"]},
    ).json()
    client.patch(
        f"/api/v1/ai/artifacts/{artifact_id}/drafts/{draft['draft_id']}",
        json={"field": "city", "action": "edited", "value": "Somewhere else entirely"},
    )

    after = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    assert after["metadata"] == before["metadata"]  # metadata is untouched by accepting an edit
    # AI output is not part of the evidence report at all.
    assert "ai_drafts" not in after
    assert "Somewhere else entirely" not in json.dumps(after)


def test_drafts_and_transcripts_export_separately_and_delete(
    client: TestClient, fixtures: FixtureSet, fake_ai: FakeExtractor
) -> None:
    artifact_id, _ = analyse(client, fixtures.with_metadata)
    client.post(
        f"/api/v1/ai/artifacts/{artifact_id}/drafts",
        json={"source_kind": "metadata", "fields": ["city"]},
    )

    package = zipfile.ZipFile(io.BytesIO(client.get(f"/api/v1/artifacts/{artifact_id}/export").content))
    names = set(package.namelist())
    assert "ai/drafts.json" in names
    assert "ai/README.txt" in names
    notice = package.read("ai/README.txt").decode()
    assert "not evidence" in notice
    assert "Vestigo never" in notice
    # The evidence report itself carries no AI material.
    report = json.loads(package.read("report.json"))
    assert "ai_drafts" not in report and "transcripts" not in report
    assert "Testville" in json.dumps(json.loads(package.read("ai/drafts.json")))

    summary = client.delete(f"/api/v1/artifacts/{artifact_id}").json()
    assert summary["ai_drafts"] == 1


def test_transcription_is_opt_in_then_records_segments_and_lineage(
    client: TestClient, services: AppServices, fixtures: FixtureSet, fake_ai: FakeExtractor
) -> None:
    artifact_id = upload_ok(client, fixtures.audio_mp3)["artifact_id"]
    # Images have no audio at all.
    image_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    assert_error(
        client.post(f"/api/v1/ai/artifacts/{image_id}/transcripts", json={}), 422, "WRONG_MEDIA_TYPE"
    )

    response = client.post(f"/api/v1/ai/artifacts/{artifact_id}/transcripts", json={"language": "en"})
    assert response.status_code == 201, response.text
    transcript = response.json()
    assert transcript["transcript_id"].startswith("tsc_")
    assert transcript["text"] == "testing one two three"
    assert transcript["edited_text"] is None
    assert transcript["language"] == "en"
    assert transcript["review_state"] == "UNREVIEWED"
    assert transcript["model"]["name"] == "whistle"
    assert [segment["start"] for segment in transcript["segments"]] == [0.0, 1.5]
    assert transcript["segments"][0]["words"][0]["probability"] == 0.91

    listed = client.get(f"/api/v1/ai/artifacts/{artifact_id}/transcripts").json()
    assert "potentially inaccurate" in listed["notice"]
    assert "original audio is unchanged" in listed["notice"]

    url = f"/api/v1/ai/artifacts/{artifact_id}/transcripts/{transcript['transcript_id']}"
    edited = client.patch(url, json={"edited_text": "testing 1 2 3", "review_state": "REVIEWED"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["edited_text"] == "testing 1 2 3"
    assert edited.json()["text"] == "testing one two three"  # the model's text is preserved

    assert [event.event_type for event in events_for(services, artifact_id)] == [
        "transcript_created",
        "transcript_edited",
    ]
    assert client.delete(url).status_code == 204
    assert [event.event_type for event in events_for(services, artifact_id)][-1] == "transcript_deleted"


def test_video_transcription_keeps_the_extracted_audio_as_lineage(
    client: TestClient, fixtures: FixtureSet, fake_ai: FakeExtractor
) -> None:
    from tests.pipeline.test_video_pipeline import analyse_video

    artifact_id, _ = analyse_video(client, fixtures.video_scenes)
    transcript = client.post(f"/api/v1/ai/artifacts/{artifact_id}/transcripts", json={}).json()

    # The audio track was extracted to a derived file, so the transcript's source is explicit.
    assert transcript["derived_file_id"].startswith("df_")
    content = client.get(f"/api/v1/artifacts/{artifact_id}/derived/{transcript['derived_file_id']}/content")
    assert content.status_code == 200
    assert len(content.content) > 0
