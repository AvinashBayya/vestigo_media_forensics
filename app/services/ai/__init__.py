"""Local AI subsystem (Pass 1, D24; made live in D27).

Importing this package sets the vendor telemetry kill-switch and the offline switch and nothing
else: no model is loaded, no network is touched, and the third-party runtime is not imported until a
provider is actually asked to do work and the analyst has enabled the feature.

The resolvers below are the single seam where settings become providers, so tests replace one
function rather than patching a vendor library.
"""

from pathlib import Path

from app.services.ai.protocols import (
    EmbeddingResult,
    ExtractedField,
    ExtractionResult,
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
    DEFAULT_GENERATION,
    KNOWN_MODELS,
    MODEL_SUFFIX,
    OFFLINE_ENV,
    RUNTIME_MODULE,
    RUNTIME_PACKAGE,
    TELEMETRY_ENV,
    AIUnavailableError,
    ModelInfo,
    engine_available,
    engine_library_path,
    engine_unavailable_reason,
    file_digest,
    find_model,
    model_for_path,
    offline_enforced,
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
    "DEFAULT_GENERATION",
    "KNOWN_MODELS",
    "LOCAL_EMBEDDER_MODEL",
    "MODEL_SUFFIX",
    "OFFLINE_ENV",
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
    "engine_available",
    "engine_library_path",
    "engine_unavailable_reason",
    "file_digest",
    "find_model",
    "model_for_path",
    "model_state",
    "offline_enforced",
    "resolve_embedder",
    "resolve_extractor",
    "resolve_model_installed",
    "resolve_transcriber",
    "runtime_installed",
    "telemetry_disabled",
    "unavailable_reason",
]


def _model_path(raw: str | None) -> Path | None:
    """The configured model file, or None when nothing usable is configured."""
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_file() else None


def _configured(raw: str | None, label: str) -> tuple[Path | None, str | None]:
    """Tell apart "nothing configured" from "configured, but the file is not there".

    Nothing configured is normal: the engine then loads the model it carries. A path that does not
    resolve is a mistake worth reporting, because the alternative is reporting the feature as
    available and then failing on first use.
    """
    if not raw:
        return None, None
    path = Path(raw).expanduser()
    if path.is_file():
        return path, None
    return None, (
        f"{label} is on, but the configured model file is not there: {raw}. "
        "Correct the path in Settings, or clear it to use the model the engine carries."
    )


def unavailable_reason(provider: object) -> str | None:
    """Why a provider cannot work, or None. The one place callers ask."""
    reason = getattr(provider, "unavailable_reason", None)
    return reason if isinstance(reason, str) else None


def resolve_extractor(*, enabled: bool, model_path: str | None):
    """The extraction provider for the current settings: Needle, or a refusal with the reason."""
    if not enabled:
        return DisabledProvider()
    if not runtime_installed():
        return DisabledProvider(
            f"Local AI is on, but the runtime is not installed (pip install {RUNTIME_PACKAGE})."
        )
    path, problem = _configured(model_path, "Local AI")
    if problem is not None:
        return DisabledProvider(problem)
    provider = NeedleExtractor(path)
    reason = provider.unavailable_reason
    return DisabledProvider(reason) if reason else provider


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
    path, problem = _configured(model_path, "Transcription")
    if problem is not None:
        return DisabledProvider(problem)
    provider = NeedleTranscriber(path)
    reason = provider.unavailable_reason
    return DisabledProvider(reason) if reason else provider


def resolve_embedder(*, enabled: bool) -> LocalHashEmbedder | DisabledProvider:
    """The embedder for semantic search.

    The dependency-free local embedder is used even when the runtime is installed. This was verified,
    not assumed (D27): the runtime's text embedding call exists but raises "embeddings require a
    Needle 3 model", and the vendor publishes no generation 3 engine, so no model vectors can be
    produced here at all. Swapping them in later is a change in this function and nowhere else,
    because the index records the model that produced every chunk.
    """
    if not enabled:
        return DisabledProvider(
            "Semantic search is turned off. Enable it in Settings to index your own notes and text."
        )
    return LocalHashEmbedder()


def _configured_paths(editable: object) -> dict[str, str]:
    """Which configured path, if any, belongs to each known model."""
    drafts = getattr(editable, "ai_model_path", "") or ""
    speech = getattr(editable, "transcription_model_path", "") or ""
    return {"needle2": drafts, "needle3": drafts, "whistle": speech}


def resolve_model_installed(name: str, editable: object) -> bool:
    """Whether a local file is in place for this model, per the analyst's configured paths."""
    return _model_path(_configured_paths(editable).get(name)) is not None


def model_state(model: ModelInfo, editable: object) -> dict[str, object]:
    """What an analyst needs to know about one known model: is its file here, and can it run?

    `installed` is about a file; `runnable` is about the engine that would load it. They are separate
    because the common case on this platform is a model whose weights are published and whose engine
    is not, and saying "installed" for that would be a lie.
    """
    generation = model.generation if model.generation is not None else DEFAULT_GENERATION
    reason = engine_unavailable_reason(generation)
    return {
        "installed": resolve_model_installed(model.name, editable),
        "runnable": reason is None,
        "unavailable_reason": reason,
    }
