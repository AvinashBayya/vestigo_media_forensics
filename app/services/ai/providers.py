"""AI providers (Pass 1): the disabled default, a dependency-free embedder, and Needle.

`disabled` is what a stock Vestigo uses: every call raises with a clear reason, so the feature is
visibly absent rather than silently degraded. `LocalHashEmbedder` needs no model and no network, so
semantic search is useful on day one and upgrades to model vectors when the runtime is installed.
`Needle*` providers import the third-party runtime lazily, inside the call, after the telemetry
kill-switch in `runtime` has already run.
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
    GenerationResult,
    TranscriptionResult,
    TranscriptSegment,
)
from app.services.ai.runtime import (
    RUNTIME_MODULE,
    AIUnavailableError,
    ModelInfo,
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

    def generate(self, prompt: str) -> GenerationResult:
        return self._refuse()

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

    def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(vectors=[self._vector(text) for text in texts], model=LOCAL_EMBEDDER_MODEL)


def cosine(left: list[float], right: list[float]) -> float:
    """Both sides are stored normalised, so this is a dot product clamped to [-1, 1]."""
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))


class NeedleExtractor:
    """Structured extraction with Needle: the declared fields are the shape it must fill."""

    def __init__(self, model_path: Path | None = None) -> None:
        self._model_path = model_path

    def extract(self, text: str, fields: list[str]) -> ExtractionResult:
        needle = imported_runtime()
        model = (
            model_for_path(self._model_path, "needle3")
            if self._model_path is not None
            else (find_model("needle3") or ModelInfo("needle3", None, None, None, None, RUNTIME_MODULE))
        )
        try:
            raw = needle.extract(text, fields) if hasattr(needle, "extract") else None
            if raw is None:
                agent = needle.Needle()
                raw = agent.run(
                    "Extract exactly these fields from the text, leaving a field out when the text "
                    f"does not state it. Fields: {', '.join(fields)}.\n\nText:\n{text}"
                )
        except AIUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - a model failure is reported, never hidden
            raise AIUnavailableError(f"The model could not complete the extraction: {exc}") from exc
        return _extraction_from_raw(raw, fields, model)


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

    def __init__(self, model_path: Path | None = None) -> None:
        self._model_path = model_path

    def transcribe(self, audio_path: Path, language: str | None = None) -> TranscriptionResult:
        needle = imported_runtime()
        model = (
            model_for_path(self._model_path, "whistle")
            if self._model_path is not None
            else (find_model("whistle") or ModelInfo("whistle", None, None, None, None, RUNTIME_MODULE))
        )
        options: dict[str, Any] = {"word_timestamps": True}
        if language:
            options["language"] = language
        try:
            raw = needle.transcribe(str(audio_path), **options)
        except AIUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported as a failure, never silently empty
            raise AIUnavailableError(f"The model could not transcribe the audio: {exc}") from exc
        return _transcription_from_raw(raw, model)


def _transcription_from_raw(raw: Any, model: ModelInfo) -> TranscriptionResult:
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
    if not segments and text:
        # A runtime that returns only flat text still produces a usable, honestly-timed transcript.
        segments.append(TranscriptSegment(start_seconds=0.0, end_seconds=0.0, text=text, words=[]))
    language = raw.get("language")
    duration = raw.get("duration") or raw.get("duration_seconds")
    return TranscriptionResult(
        segments=segments,
        text=text or " ".join(segment.text for segment in segments).strip(),
        language=str(language) if language else None,
        model=model,
        duration_seconds=float(duration) if isinstance(duration, int | float) else None,
        warnings=[] if segments else ["The model returned no speech for this audio."],
    )
