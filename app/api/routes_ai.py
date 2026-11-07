from fastapi import APIRouter

from app.api.deps import Services
from app.schemas.ai import AIModelInfo, AIStatus
from app.services import ai, app_settings

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status", response_model=AIStatus)
def get_ai_status(services: Services) -> AIStatus:
    """Whether local AI is available, and on exactly what terms (Pass 1, D24).

    Reports the analyst's own switches, whether the runtime is installed, which model files are in
    place, and that vendor telemetry is disabled in this process. Nothing here loads a model or
    touches the network, so the status is safe to poll."""
    editable = app_settings.get_settings_response(services).editable
    extractor = ai.resolve_extractor(enabled=editable.ai_enabled, model_path=editable.ai_model_path)
    transcriber = ai.resolve_transcriber(
        enabled=editable.transcription_enabled, model_path=editable.transcription_model_path
    )
    embedder = ai.resolve_embedder(enabled=editable.semantic_search_enabled)

    def reason(provider: object) -> str | None:
        return getattr(provider, "_reason", None)

    return AIStatus(
        runtime_package=ai.RUNTIME_PACKAGE,
        runtime_installed=ai.runtime_installed(),
        telemetry_disabled=ai.telemetry_disabled(),
        telemetry_environment=dict(ai.TELEMETRY_ENV),
        ai_enabled=editable.ai_enabled,
        transcription_enabled=editable.transcription_enabled,
        semantic_search_enabled=editable.semantic_search_enabled,
        drafts_available=reason(extractor) is None,
        drafts_unavailable_reason=reason(extractor),
        transcription_available=reason(transcriber) is None,
        transcription_unavailable_reason=reason(transcriber),
        semantic_search_available=reason(embedder) is None,
        semantic_search_unavailable_reason=reason(embedder),
        label=ai.AI_LABEL,
        limitations=list(ai.AI_LIMITATIONS),
        known_models=[
            AIModelInfo(
                **model.as_dict(),
                installed=ai.resolve_model_installed(model.name, editable),
            )
            for model in ai.KNOWN_MODELS
        ],
    )
