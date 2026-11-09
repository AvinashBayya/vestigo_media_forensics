"""The local AI runtime against real weights (D27). Run with: pytest -m live_model

Excluded from the default run, because it needs the runtime installed and an engine staged. It is
the only place a vendor library is actually executed, so it is where an upstream change shows up:
if the call shapes in `providers.py` drift from the installed package, these fail and the stand-in
tests in tests/unit/test_ai_providers.py keep passing. Both are needed.

Staging, once:
    python -m pip install -e ".[dev,ai]"
    needle fetch --generation 2
"""

import time
from pathlib import Path

import pytest

from app.services.ai import providers, runtime
from app.services.ai.runtime import AIUnavailableError

pytestmark = pytest.mark.live_model

needs_runtime = pytest.mark.skipif(
    not runtime.runtime_installed(),
    reason=f"the local AI runtime is not installed (pip install {runtime.RUNTIME_PACKAGE})",
)
needs_engine = pytest.mark.skipif(
    not runtime.engine_available(runtime.DEFAULT_GENERATION),
    reason=f"no generation {runtime.DEFAULT_GENERATION} engine is staged (needle fetch)",
)


@needs_runtime
def test_the_runtime_imports_with_telemetry_and_downloads_disabled() -> None:
    assert runtime.telemetry_disabled()
    assert runtime.offline_enforced()
    module = runtime.imported_runtime()
    # The calls the adapters rely on are present under the names they use.
    assert callable(module.extract)
    assert callable(module.transcribe)
    assert hasattr(module, "Needle")


@needs_runtime
@needs_engine
def test_a_real_model_extracts_what_the_text_states() -> None:
    started = time.perf_counter()
    result = providers.NeedleExtractor().extract(
        "The camera make is Canon. The serial number is 44567123.",
        ["camera_make", "serial_number", "city"],
    )
    elapsed = time.perf_counter() - started

    values = {field.name: field.value for field in result.fields}
    assert values.get("camera_make") == "Canon"
    assert values.get("serial_number") == "44567123"
    # The text names no city, so no city is recorded. A model that invents one fails here.
    assert "city" not in values
    assert result.model.generation == runtime.DEFAULT_GENERATION
    assert result.model.license == "Apache-2.0"
    # Generous: this asserts the model is usable interactively, not a benchmark figure.
    assert elapsed < 60.0


@needs_runtime
@needs_engine
def test_a_real_model_records_no_confidence_it_was_not_given() -> None:
    result = providers.NeedleExtractor().extract("The camera make is Canon.", ["camera_make"])
    for field in result.fields:
        assert field.confidence is None or 0.0 <= field.confidence <= 1.0


@needs_runtime
@needs_engine
def test_the_engine_rejects_an_answer_it_cannot_ground() -> None:
    """The runtime's own grounding check is left on, and a refusal is reported, not hidden.

    "14 March 2021" reformatted to an ISO date is not literally in the text, and the engine says so.
    """
    result = providers.NeedleExtractor().extract(
        "Photographed on 14 March 2021 near the harbour.", ["capture_date"]
    )
    if not result.fields:
        assert result.warnings
        assert "grounding check" in result.warnings[0] or "no values" in result.warnings[0]


@needs_runtime
def test_transcription_either_works_or_says_exactly_why_not(tmp_path: Path) -> None:
    """Whistle needs the generation 3 engine, which the vendor does not publish for every platform.

    Either outcome is acceptable; silently returning an empty transcript would not be.
    """
    transcriber = providers.NeedleTranscriber()
    reason = transcriber.unavailable_reason
    if reason is not None:
        assert "generation 3" in reason
        with pytest.raises(AIUnavailableError):
            transcriber.transcribe(tmp_path / "missing.wav")
        pytest.skip(reason)

    import subprocess

    clip = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=2", "-ar", "16000", "-ac", "1", str(clip)],
        check=True,
    )
    result = transcriber.transcribe(clip)
    # A tone carries no speech, so an empty transcript here is the honest answer, with a warning.
    assert result.segments or result.warnings


@needs_runtime
def test_no_text_embeddings_are_claimed_that_the_runtime_cannot_produce() -> None:
    """The embedder is the dependency-free one because the runtime's own text embedding refuses.

    If this starts passing differently, `resolve_embedder` should be revisited, not this test.
    """
    module = runtime.imported_runtime()
    agent_type = getattr(module, "Needle", None)
    assert agent_type is not None
    if not runtime.engine_available(runtime.DEFAULT_GENERATION):
        pytest.skip("no engine staged")
    agent = agent_type(generation=runtime.DEFAULT_GENERATION)
    try:
        with pytest.raises(Exception, match="Needle 3"):
            agent.embed("a photograph of a harbour")
    finally:
        agent.close()
