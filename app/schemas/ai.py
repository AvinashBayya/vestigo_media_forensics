"""Local AI status and provenance schemas (Pass 1, D24)."""

from pydantic import BaseModel


class AIModelInfo(BaseModel):
    """Provenance for a model, as the vendor states it. Vestigo verifies none of these claims."""

    name: str
    version: str | None = None
    quantization: str | None = None
    source_url: str | None = None
    license: str | None = None
    runtime: str
    local_path: str | None = None
    # Whether a local file for this model is in place on this machine.
    installed: bool = False


class AIStatus(BaseModel):
    """What local AI can do right now, and why anything unavailable is unavailable."""

    runtime_package: str
    runtime_installed: bool
    # Vendor telemetry is forced off in-process before the runtime can load (D24).
    telemetry_disabled: bool
    telemetry_environment: dict[str, str]
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
