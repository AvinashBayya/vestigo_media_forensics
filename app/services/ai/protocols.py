"""Provider protocols for local AI work (Pass 1).

Each capability is a small protocol so the real runtime, a dependency-free fallback, and the test
fakes are interchangeable. Providers return data plus the `ModelInfo` that produced it, so every
stored artifact carries its own provenance and nothing has to be inferred later.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.services.ai.runtime import ModelInfo


@dataclass
class ExtractedField:
    """One field a model proposed. `confidence` is set only when the model supplied one."""

    name: str
    value: str
    confidence: float | None = None


@dataclass
class ExtractionResult:
    fields: list[ExtractedField]
    model: ModelInfo
    # The model's own reasoning text, when it returns one. Never presented as a finding.
    reasoning: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class TranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str
    # Word-level timing where the model provides it: [{"word", "start", "end", "probability"}].
    words: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TranscriptionResult:
    segments: list[TranscriptSegment]
    text: str
    language: str | None
    model: ModelInfo
    duration_seconds: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: ModelInfo


# Every provider says why it cannot work, so callers never inspect a private attribute. None means
# the provider is ready; a string is a reason fit to show an analyst.
class Provider(Protocol):
    @property
    def unavailable_reason(self) -> str | None: ...


class FieldExtractor(Provider, Protocol):
    def extract(self, text: str, fields: list[str]) -> ExtractionResult: ...


class Transcriber(Provider, Protocol):
    def transcribe(self, audio_path: Path, language: str | None = None) -> TranscriptionResult: ...


class TextEmbedder(Provider, Protocol):
    def embed(self, texts: list[str]) -> EmbeddingResult: ...

    @property
    def dimensions(self) -> int: ...


# There is deliberately no text-generation protocol: the runtime exposes no free-text generation
# (`complete()` with no tools returns an empty call), so Vestigo does not pretend to offer one.
