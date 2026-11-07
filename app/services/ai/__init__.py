"""Local AI subsystem (Pass 1, D24).

Importing this package sets the vendor telemetry kill-switch and nothing else: no model is loaded,
no network is touched, and the third-party runtime is not imported until a provider is actually
asked to do work and the analyst has enabled the feature.
"""

from pathlib import Path

from app.services.ai.protocols import (
    EmbeddingResult,
    ExtractedField,
    ExtractionResult,
    GenerationResult,
    TranscriptionResult,
    TranscriptSegment,
)
from app.services.ai.providers import (
    DISABLED_REASON,
    LOCAL_EMBEDDER_MODEL,
    DisabledProvider,
    LocalHashEmbedder,
    NeedleExtractor,
    NeedleTranscriber,
    cosine,
)
from app.services.ai.runtime import (
    AI_LABEL,
    AI_LIMITATIONS,
    KNOWN_MODELS,
    RUNTIME_MODULE,
    RUNTIME_PACKAGE,
    TELEMETRY_ENV,
    AIUnavailableError,
    ModelInfo,
    find_model,
    model_for_path,
    runtime_installed,
    telemetry_disabled,
)

__all__ = [
    "AIUnavailableError",
    "AI_LABEL",
    "AI_LIMITATIONS",
    "DISABLED_REASON",
    "DisabledProvider",
    "EmbeddingResult",
    "ExtractedField",
    "ExtractionResult",
    "KNOWN_MODELS",
    "GenerationResult",
    "LOCAL_EMBEDDER_MODEL",
    "LocalHashEmbedder",
    "ModelInfo",
    "NeedleExtractor",
    "NeedleTranscriber",
    "RUNTIME_MODULE",
    "RUNTIME_PACKAGE",
    "TELEMETRY_ENV",
    "TranscriptSegment",
    "TranscriptionResult",
    "cosine",
    "find_model",
    "model_for_path",
    "resolve_embedder",
    "resolve_model_installed",
    "resolve_extractor",
    "resolve_transcriber",
    "runtime_installed",
    "telemetry_disabled",
]


def _model_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_file() else None


def resolve_extractor(*, enabled: bool, model_path: str | None):
    """The extraction provider for the current settings: Needle, or a refusal with the reason."""
    if not enabled:
        return DisabledProvider()
    if not runtime_installed():
        return DisabledProvider(
            f"Local AI is on, but the runtime is not installed (pip install {RUNTIME_PACKAGE})."
        )
    return NeedleExtractor(_model_path(model_path))


def resolve_transcriber(*, enabled: bool, model_path: str | None):
    """The transcription provider. Transcription has its own setting, separate from AI drafts."""
    if not enabled:
        return DisabledProvider(
            "Transcription is turned off. Enable it in Settings; audio stays on this machine."
        )
    if not runtime_installed():
        return DisabledProvider(
            f"Transcription is on, but the runtime is not installed (pip install {RUNTIME_PACKAGE})."
        )
    return NeedleTranscriber(_model_path(model_path))


def resolve_embedder(*, enabled: bool) -> LocalHashEmbedder | DisabledProvider:
    """The embedder for semantic search.

    The dependency-free local embedder is used even when the runtime is installed: the published
    Python API exposes audio embeddings but no confirmed text-embedding call, and Vestigo will not
    pretend to use a model it cannot verify. Swapping in Needle text vectors later is a change here
    and nowhere else, because the index records the model that produced every chunk.
    """
    if not enabled:
        return DisabledProvider(
            "Semantic search is turned off. Enable it in Settings to index your own notes and text."
        )
    return LocalHashEmbedder()


def resolve_model_installed(name: str, editable: object) -> bool:
    """Whether a local file is in place for this model, per the analyst's configured paths."""
    paths = {
        "needle3": getattr(editable, "ai_model_path", "") or "",
        "whistle": getattr(editable, "transcription_model_path", "") or "",
    }
    return _model_path(paths.get(name)) is not None
