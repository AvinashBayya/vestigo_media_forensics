"""The Needle adapters, exercised against a stand-in runtime (D27).

These tests exist because the adapters were written from vendor prose and were never executed: the
package is optional, so nothing in the suite had ever called `NeedleExtractor.extract`. A fake module
is injected into `sys.modules` under the runtime's import name, which covers the mapping and error
handling on every machine, installed or not. The real library is exercised separately by the
`live_model` tests.

The shapes asserted here are the shapes the installed runtime actually returns, recorded in D27:
`extract` hands back a plain arguments mapping, and `transcribe` hands back flat text plus a `words`
list, never `segments`.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

from app.services.ai import providers
from app.services.ai.runtime import AIUnavailableError


class FakeNeedle:
    """Enough of the runtime to drive the adapters: records its calls, returns what it is given."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def extract(self, text: str, schema: Any, **options: Any) -> Any:
        self.calls.append({"call": "extract", "text": text, "schema": schema, **options})
        if self.error is not None:
            raise self.error
        return self.result

    def transcribe(self, audio: str, **options: Any) -> Any:
        self.calls.append({"call": "transcribe", "audio": audio, **options})
        if self.error is not None:
            raise self.error
        return self.result


class FakeValidationError(Exception):
    """Stands in for the runtime's ExtractionValidationError, which is matched by class name."""


FakeValidationError.__name__ = "ExtractionValidationError"


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch):
    """Put a stand-in runtime behind the adapters, and report its engine as staged."""

    def place(fake: FakeNeedle, *, engine: bool = True) -> FakeNeedle:
        monkeypatch.setitem(sys.modules, "needle", fake)
        monkeypatch.setattr(providers, "imported_runtime", lambda: fake)
        monkeypatch.setattr(providers, "engine_available", lambda generation=2: engine)
        monkeypatch.setattr(
            providers,
            "engine_unavailable_reason",
            lambda generation=2: None if engine else f"no generation {generation} engine here",
        )
        return fake

    return place


def test_extractor_sends_a_schema_and_keeps_only_stated_fields(install) -> None:
    fake = install(FakeNeedle({"camera_make": "Canon", "serial_number": "44567123"}))
    result = providers.NeedleExtractor().extract("some text", ["camera_make", "serial_number", "city"])

    schema = fake.calls[0]["schema"]
    assert schema["parameters"]["type"] == "object"
    assert set(schema["parameters"]["properties"]) == {"camera_make", "serial_number", "city"}
    assert fake.calls[0]["strict"] is True
    # The field the runtime did not fill is absent rather than empty: Vestigo records no blanks.
    assert [(field.name, field.value) for field in result.fields] == [
        ("camera_make", "Canon"),
        ("serial_number", "44567123"),
    ]
    assert result.warnings == []


def test_extractor_reports_an_empty_answer_rather_than_pretending(install) -> None:
    install(FakeNeedle({}))
    result = providers.NeedleExtractor().extract("text", ["camera_make"])
    assert result.fields == []
    assert result.warnings == ["The model returned no values for the requested fields."]


def test_extractor_records_a_grounding_refusal_as_a_warning(install) -> None:
    """The engine's own check rejecting an answer is a result, not a crash."""
    install(FakeNeedle(error=FakeValidationError("values not grounded in the input: capture_date")))
    result = providers.NeedleExtractor().extract("text", ["capture_date"])
    assert result.fields == []
    assert "grounding check" in result.warnings[0]
    assert "capture_date" in result.warnings[0]


def test_extractor_turns_a_model_failure_into_an_unavailable_reason(install) -> None:
    install(FakeNeedle(error=RuntimeError("engine exploded")))
    with pytest.raises(AIUnavailableError) as raised:
        providers.NeedleExtractor().extract("text", ["camera_make"])
    assert "engine exploded" in raised.value.reason


def test_extractor_refuses_before_the_runtime_can_reach_for_an_engine(install) -> None:
    fake = install(FakeNeedle({"camera_make": "Canon"}), engine=False)
    with pytest.raises(AIUnavailableError) as raised:
        providers.NeedleExtractor().extract("text", ["camera_make"])
    assert "no generation 2 engine here" in raised.value.reason
    assert fake.calls == []  # nothing was attempted, so nothing could be downloaded


def test_extractor_passes_a_configured_archive_as_weights(install, tmp_path: Path) -> None:
    archive = tmp_path / "needle2.cact"
    archive.write_bytes(b"not a real model")
    fake = install(FakeNeedle({"camera_make": "Canon"}))
    result = providers.NeedleExtractor(archive).extract("text", ["camera_make"])

    assert fake.calls[0]["weights"] == str(archive)
    assert "generation" not in fake.calls[0]  # the archive header decides, not Vestigo
    # Provenance names the exact bytes behind the draft.
    assert result.model.local_path == str(archive)
    assert result.model.size_bytes == len(b"not a real model")
    assert result.model.sha256


def test_extractor_records_only_a_model_supplied_confidence(install) -> None:
    install(FakeNeedle({"fields": {"camera_make": "Canon"}, "confidence": 0.5}))
    result = providers.NeedleExtractor().extract("text", ["camera_make"])
    assert [field.confidence for field in result.fields] == [0.5]

    install(FakeNeedle({"camera_make": "Canon"}))
    bare = providers.NeedleExtractor().extract("text", ["camera_make"])
    # No confidence from the model means none recorded, never a number Vestigo made up.
    assert [field.confidence for field in bare.fields] == [None]


def test_transcriber_builds_segments_from_word_timings(install, tmp_path: Path) -> None:
    """The real runtime returns flat text and a word list, so the segment is timed from the words."""
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF")
    fake = install(
        FakeNeedle(
            {
                "text": "hello there",
                "language": "en",
                "words": [
                    {"start": 0.4, "end": 0.9, "probability": 0.98},
                    {"start": 1.0, "end": 1.6, "probability": 0.91},
                ],
            }
        )
    )
    result = providers.NeedleTranscriber().transcribe(audio, "en")

    assert fake.calls[0]["word_timestamps"] is True
    assert fake.calls[0]["language"] == "en"
    assert result.text == "hello there"
    assert result.language == "en"
    assert len(result.segments) == 1
    assert result.segments[0].start_seconds == 0.4
    assert result.segments[0].end_seconds == 1.6
    assert len(result.segments[0].words) == 2
    # Duration is the measured end of the last word, not an estimate.
    assert result.duration_seconds == 1.6


def test_transcriber_still_accepts_a_segment_shape(install, tmp_path: Path) -> None:
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF")
    install(
        FakeNeedle(
            {
                "text": "one two",
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "one", "words": []},
                    {"start": 1.0, "end": 2.0, "text": "two", "words": []},
                ],
            }
        )
    )
    result = providers.NeedleTranscriber().transcribe(audio)
    assert [segment.text for segment in result.segments] == ["one", "two"]


def test_transcriber_reports_silence_rather_than_inventing_speech(install, tmp_path: Path) -> None:
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF")
    install(FakeNeedle({"text": "", "words": []}))
    result = providers.NeedleTranscriber().transcribe(audio)
    assert result.segments == []
    assert result.warnings == ["The model returned no speech for this audio."]


def test_transcriber_refuses_when_its_engine_is_absent(install, tmp_path: Path) -> None:
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF")
    fake = install(FakeNeedle({"text": "hello"}), engine=False)
    with pytest.raises(AIUnavailableError) as raised:
        providers.NeedleTranscriber().transcribe(audio)
    assert "no generation 3 engine here" in raised.value.reason
    assert fake.calls == []


def test_mapping_handles_the_shapes_the_runtime_can_return() -> None:
    assert providers._as_mapping({"camera_make": "Canon"}) == {"camera_make": "Canon"}
    assert providers._as_mapping({"arguments": {"a": "1"}}) == {"a": "1"}
    assert providers._as_mapping({"results": [{"a": "1"}]}) == {"a": "1"}
    assert providers._as_mapping({"function_calls": [{"arguments": {"a": "1"}}]}) == {"a": "1"}
    assert providers._as_mapping("not a mapping") == {}
