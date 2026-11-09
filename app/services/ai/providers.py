"""AI providers: the disabled default, a dependency-free embedder, and Needle.

`DisabledProvider` is what a stock Vestigo uses: every call raises with a clear reason, so the
feature is visibly absent rather than silently degraded. `LocalHashEmbedder` needs no model and no
network, so semantic search is useful on day one. `Needle*` providers import the third-party runtime
lazily, inside the call, after the telemetry and offline switches in `runtime` have already run.

The call shapes here were verified against cactus-needle 3.2.10 rather than taken from vendor prose
(D27): `needle.extract(text, schema, weights=, generation=, strict=)` takes an OpenAI-style tool
schema and returns the plain arguments mapping, and `needle.transcribe` returns flat text with a
`words` list, not segments. Every call is made under `ENGINE_LOCK`, because the engine loads one
model per process and its native library is not thread-safe.
"""

import hashlib
import math
import re
from pathlib import Path
from typing import Any

from app.services.ai.protocols import (
    EmbeddingResult,
    ExtractedField,
    ExtractionResult,
    TranscriptionResult,
    TranscriptSegment,
)
from app.services.ai.runtime import (
    DEFAULT_GENERATION,
    ENGINE_LOCK,
    RUNTIME_MODULE,
    AIUnavailableError,
    ModelInfo,
    engine_available,
    engine_unavailable_reason,
    find_model,
    imported_runtime,
    model_for_path,
)

DISABLED_REASON = (
    "Local AI is turned off. Enable it in Settings and point Vestigo at a local model file; "
    "nothing is downloaded or sent anywhere."
)


class DisabledProvider:
    """Every capability, refused with the same clear reason. The default in a stock build."""

    def __init__(self, reason: str = DISABLED_REASON) -> None:
        self._reason = reason

    def _refuse(self) -> Any:
        raise AIUnavailableError(self._reason)

    def extract(self, text: str, fields: list[str]) -> ExtractionResult:
        return self._refuse()

    def transcribe(self, audio_path: Path, language: str | None = None) -> TranscriptionResult:
        return self._refuse()

    def embed(self, texts: list[str]) -> EmbeddingResult:
        return self._refuse()

    @property
    def unavailable_reason(self) -> str | None:
        """Why this provider refuses. Callers read this instead of a private attribute."""
        return self._reason

    @property
    def dimensions(self) -> int:
        return 0


_WORD = re.compile(r"[\w']+", re.UNICODE)

LOCAL_EMBEDDER_MODEL = ModelInfo(
    name="vestigo-local-hash",
    version="1",
    quantization=None,
    source_url=None,
    license="Part of Vestigo",
    runtime="python",
)


class LocalHashEmbedder:
    """Deterministic bag-of-words hashing vectors: no model, no network, no new dependency.

    This is lexical, not semantic: it matches shared wording, not meaning, and the search UI says so.
    It exists so semantic search over the analyst's own material works in a stock build, and so the
    index, storage, deletion, and UI are exercised by tests without any model present.
    """

    def __init__(self, dimensions: int = 256) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _vector(self, text: str) -> list[float]:
        counts: dict[int, float] = {}
        words = _WORD.findall(text.casefold())
        for word in words:
            digest = hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "big") % self._dimensions
            counts[bucket] = counts.get(bucket, 0.0) + 1.0
        vector = [0.0] * self._dimensions
        for bucket, count in counts.items():
            # Sub-linear term weighting, so one repeated word cannot dominate a chunk.
            vector[bucket] = 1.0 + math.log(count)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    @property
    def unavailable_reason(self) -> str | None:
        return None

    def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(vectors=[self._vector(text) for text in texts], model=LOCAL_EMBEDDER_MODEL)


def cosine(left: list[float], right: list[float]) -> float:
    """Both sides are stored normalised, so this is a dot product clamped to [-1, 1]."""
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))


class NeedleExtractor:
    """Structured extraction with Needle: the declared fields are the schema it must fill.

    The runtime takes an OpenAI-style tool schema, not a list of names, and returns only the
    arguments it filled, so a field the text does not state is simply absent. Its `strict` grounding
    check is left on: it refuses values that contradict or are not present in the input, which is the
    behaviour Vestigo wants, and a refusal is reported as a warning rather than hidden.
    """

    CAPABILITY = "drafts"

    def __init__(self, model_path: Path | None = None) -> None:
        self._model_path = model_path

    @property
    def unavailable_reason(self) -> str | None:
        return None if self._model_path is not None else engine_unavailable_reason(DEFAULT_GENERATION)

    def extract(self, text: str, fields: list[str]) -> ExtractionResult:
        needle = imported_runtime()
        model = (
            model_for_path(self._model_path, f"needle{DEFAULT_GENERATION}")
            if self._model_path is not None
            else _known_or_bare(f"needle{DEFAULT_GENERATION}", DEFAULT_GENERATION)
        )
        _require_engine(needle, self._model_path, DEFAULT_GENERATION)
        schema = _fields_schema(fields)
        options: dict[str, Any] = {"strict": True}
        if self._model_path is not None:
            # An explicit archive also keeps the engine from consulting (and pinging) its weights cache.
            options["weights"] = str(self._model_path)
        else:
            options["generation"] = DEFAULT_GENERATION
        try:
            with ENGINE_LOCK:
                raw = needle.extract(text, schema, **options)
        except AIUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - a model failure is reported, never hidden
            if type(exc).__name__ == "ExtractionValidationError":
                # The engine's own grounding check rejected the answer. That is a result, not a fault.
                return ExtractionResult(
                    fields=[],
                    model=model,
                    reasoning=None,
                    warnings=[
                        "The model proposed values that its own grounding check could not find in "
                        f"the text, so none were kept: {exc}"
                    ],
                )
            raise AIUnavailableError(f"The model could not complete the extraction: {exc}") from exc
        return _extraction_from_raw(raw, fields, model)


def _known_or_bare(name: str, generation: int) -> ModelInfo:
    """Recorded provenance for a model the engine loads itself, with no file of its own."""
    return find_model(name) or ModelInfo(
        name=name,
        version=None,
        quantization=None,
        source_url=None,
        license=None,
        runtime=RUNTIME_MODULE,
        generation=generation,
    )


def _require_engine(needle: Any, model_path: Path | None, default_generation: int) -> None:
    """Refuse with the real reason before the runtime tries, and fails, to fetch an engine."""
    generation = default_generation
    if model_path is not None:
        # The archive header names the generation it needs. Private helper, guarded: without it the
        # call below simply proceeds and any failure is reported as a model failure instead.
        reader = getattr(needle, "_weight_generation", None)
        if callable(reader):
            try:
                generation = int(reader(str(model_path)))
            except Exception:  # noqa: BLE001 - an unreadable header is not worth a different error
                generation = default_generation
    if not engine_available(generation):
        raise AIUnavailableError(engine_unavailable_reason(generation) or "The local AI engine is absent.")


def _fields_schema(fields: list[str]) -> dict[str, Any]:
    """The tool schema the runtime fills: one optional string per requested field, nothing else."""
    return {
        "name": "record_fields",
        "description": "Record only the fields that the text states. Leave out anything it does not.",
        "parameters": {
            "type": "object",
            "properties": {name: {"type": "string"} for name in fields},
        },
    }


def _as_mapping(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        for key in ("fields", "arguments", "result", "results"):
            inner = raw.get(key)
            if isinstance(inner, dict):
                return inner
            if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                return inner[0]
        calls = raw.get("function_calls")
        if isinstance(calls, list) and calls and isinstance(calls[0], dict):
            arguments = calls[0].get("arguments")
            if isinstance(arguments, dict):
                return arguments
        # `needle.extract` returns the arguments mapping itself, which lands here.
        return {key: value for key, value in raw.items() if not isinstance(value, dict | list)}
    return {}


def _extraction_from_raw(raw: Any, fields: list[str], model: ModelInfo) -> ExtractionResult:
    """Map whatever the runtime returned onto the declared fields, keeping only what it stated."""
    mapping = _as_mapping(raw)
    confidence = raw.get("confidence") if isinstance(raw, dict) else None
    shared = float(confidence) if isinstance(confidence, int | float) else None
    extracted: list[ExtractedField] = []
    for name in fields:
        if name not in mapping or mapping[name] in (None, ""):
            continue
        value = mapping[name]
        extracted.append(
            ExtractedField(
                name=name,
                value=value if isinstance(value, str) else str(value),
                # Only a model-supplied confidence is ever recorded; Vestigo never invents one.
                confidence=shared,
            )
        )
    reasoning = raw.get("reasoning") if isinstance(raw, dict) else None
    warnings = [] if extracted else ["The model returned no values for the requested fields."]
    return ExtractionResult(
        fields=extracted,
        model=model,
        reasoning=reasoning if isinstance(reasoning, str) else None,
        warnings=warnings,
    )


class NeedleTranscriber:
    """Speech-to-text with Whistle on the Needle engine. The source audio is only ever read."""

    CAPABILITY = "transcription"

    # Whistle loads through the generation 3 engine, whatever archive it is given.
    GENERATION = 3

    def __init__(self, model_path: Path | None = None) -> None:
        self._model_path = model_path

    @property
    def unavailable_reason(self) -> str | None:
        return engine_unavailable_reason(self.GENERATION)

    def transcribe(self, audio_path: Path, language: str | None = None) -> TranscriptionResult:
        needle = imported_runtime()
        model = (
            model_for_path(self._model_path, "whistle")
            if self._model_path is not None
            else _known_or_bare("whistle", self.GENERATION)
        )
        if not engine_available(self.GENERATION):
            raise AIUnavailableError(
                engine_unavailable_reason(self.GENERATION) or "The local AI engine is absent."
            )
        options: dict[str, Any] = {"word_timestamps": True}
        if language:
            options["language"] = language
        if self._model_path is not None:
            options["weights"] = str(self._model_path)
        try:
            with ENGINE_LOCK:
                raw = needle.transcribe(str(audio_path), **options)
        except AIUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported as a failure, never silently empty
            raise AIUnavailableError(f"The model could not transcribe the audio: {exc}") from exc
        return _transcription_from_raw(raw, model)


def _word_timings(words: list[dict[str, Any]]) -> tuple[float, float]:
    """The span a run of words covers, from the runtime's own per-word start and end."""
    starts = [float(word["start"]) for word in words if isinstance(word.get("start"), int | float)]
    ends = [float(word["end"]) for word in words if isinstance(word.get("end"), int | float)]
    return (min(starts) if starts else 0.0, max(ends) if ends else 0.0)


def _transcription_from_raw(raw: Any, model: ModelInfo) -> TranscriptionResult:
    """Build segments from whatever timing the runtime gave, and never invent any.

    The verified runtime returns flat text plus a `words` list of {start, end, probability}; older
    and other shapes return `segments`. Both are handled, and when there is no timing at all the one
    segment is honestly stamped 0.0 rather than estimated.
    """
    if not isinstance(raw, dict):
        return TranscriptionResult(segments=[], text=str(raw or ""), language=None, model=model, warnings=[])
    segments: list[TranscriptSegment] = []
    for item in raw.get("segments") or []:
        if not isinstance(item, dict):
            continue
        words = [word for word in (item.get("words") or []) if isinstance(word, dict)]
        segments.append(
            TranscriptSegment(
                start_seconds=float(item.get("start", 0.0) or 0.0),
                end_seconds=float(item.get("end", 0.0) or 0.0),
                text=str(item.get("text", "")).strip(),
                words=words,
            )
        )
    text = str(raw.get("text", "")).strip()
    words = [word for word in (raw.get("words") or []) if isinstance(word, dict)]
    if not segments and text:
        start, end = _word_timings(words)
        segments.append(TranscriptSegment(start_seconds=start, end_seconds=end, text=text, words=words))
    language = raw.get("language")
    duration = raw.get("duration") or raw.get("duration_seconds")
    if duration is None and words:
        # The runtime reports no duration; the last word end is a measured floor, not an estimate.
        duration = _word_timings(words)[1] or None
    return TranscriptionResult(
        segments=segments,
        text=text or " ".join(segment.text for segment in segments).strip(),
        language=str(language) if language else None,
        model=model,
        duration_seconds=float(duration) if isinstance(duration, int | float) else None,
        warnings=[] if segments else ["The model returned no speech for this audio."],
    )
