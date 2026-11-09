"""Local AI status and provenance schemas (Pass 1, D24; engine reporting in D27)."""

from datetime import datetime

from pydantic import BaseModel


class AIModelInfo(BaseModel):
    """Provenance for a model, as the vendor states it. Vestigo verifies none of these claims."""

    name: str
    version: str | None = None
    quantization: str | None = None
    source_url: str | None = None
    license: str | None = None
    runtime: str
    # The engine generation these weights need.
    generation: int | None = None
    local_path: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    # Whether a local file for this model is in place on this machine.
    installed: bool = False
    # Whether the engine that would load it is staged here. A model can be installed and not
    # runnable: the vendor publishes some weights without an engine for this platform.
    runnable: bool = False
    unavailable_reason: str | None = None


class AIStatus(BaseModel):
    """What local AI can do right now, and why anything unavailable is unavailable."""

    runtime_package: str
    runtime_installed: bool
    # Vendor telemetry is forced off in-process before the runtime can load (D24).
    telemetry_disabled: bool
    telemetry_environment: dict[str, str]
    # Downloads are blocked in-process, so the runtime cannot fetch an engine or weights (D27).
    offline_enforced: bool
    offline_environment: dict[str, str]
    # The engine generation Vestigo asks for, and where its library is, when it is staged.
    engine_generation: int
    engine_available: bool
    engine_path: str | None = None
    engine_unavailable_reason: str | None = None
    ai_enabled: bool
    transcription_enabled: bool
    semantic_search_enabled: bool
    drafts_available: bool
    drafts_unavailable_reason: str | None = None
    transcription_available: bool
    transcription_unavailable_reason: str | None = None
    semantic_search_available: bool
    semantic_search_unavailable_reason: str | None = None
    # Shown on every AI output in the UI and in exports.
    label: str
    limitations: list[str]
    known_models: list[AIModelInfo] = []


class ManagedModelInfo(BaseModel):
    """A model file staged on this machine, as measured on disk."""

    name: str
    size_bytes: int
    sha256: str
    modified_at: datetime
    path: str
    # Which settings fields currently point at this file.
    configured_for: list[str] = []


class ManagedModelsResponse(BaseModel):
    """Staged model files, and where to put more of them."""

    models: list[ManagedModelInfo] = []
    models_directory: str
    notice: str
    limitations: list[str] = []
