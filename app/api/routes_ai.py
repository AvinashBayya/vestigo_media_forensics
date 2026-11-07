from fastapi import APIRouter

from app.api.deps import Services
from app.schemas.ai import AIModelInfo, AIStatus
from app.schemas.ai_drafts import AIDraftInfo, AIDraftsResponse, DraftGenerateRequest, FieldDecision
from app.schemas.semantic import AnswerRequest, AnswerResponse, IndexResult, SearchResponse
from app.schemas.transcripts import (
    TranscriptCreateRequest,
    TranscriptInfo,
    TranscriptsResponse,
    TranscriptUpdate,
)
from app.services import ai, ai_drafts, app_settings, semantic, transcripts

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


@router.get("/artifacts/{artifact_id}/drafts", response_model=AIDraftsResponse)
def list_ai_drafts(services: Services, artifact_id: str) -> AIDraftsResponse:
    """The AI drafts held for this artifact, newest first (Pass 1). Drafts are never evidence."""
    return AIDraftsResponse(artifact_id=artifact_id, drafts=ai_drafts.get_drafts(services, artifact_id))


@router.post("/artifacts/{artifact_id}/drafts", response_model=AIDraftInfo, status_code=201)
def create_ai_draft(services: Services, artifact_id: str, request: DraftGenerateRequest) -> AIDraftInfo:
    """Ask the local model to propose the named fields from held material (OCR text, analyst notes,
    metadata, or a transcript). Nothing is written back over metadata or evidence. 409 with a clear
    reason when local AI is off or the runtime is not installed."""
    return ai_drafts.generate_draft(services, artifact_id, request)


@router.patch("/artifacts/{artifact_id}/drafts/{draft_id}", response_model=AIDraftInfo)
def decide_ai_draft_field(
    services: Services, artifact_id: str, draft_id: str, decision: FieldDecision
) -> AIDraftInfo:
    """Accept, edit, or reject one proposed field. The model's own value is always kept beside the
    analyst's, and the decision is recorded as a custody event."""
    return ai_drafts.decide_field(services, artifact_id, draft_id, decision)


@router.delete("/artifacts/{artifact_id}/drafts/{draft_id}", status_code=204)
def delete_ai_draft(services: Services, artifact_id: str, draft_id: str) -> None:
    """Delete a draft. The deletion stays in the custody trail."""
    ai_drafts.delete_draft(services, artifact_id, draft_id)


@router.get("/artifacts/{artifact_id}/transcripts", response_model=TranscriptsResponse)
def list_transcripts(services: Services, artifact_id: str) -> TranscriptsResponse:
    """Machine transcripts held for this artifact, newest first (Pass 1). Never evidence."""
    return TranscriptsResponse(
        artifact_id=artifact_id, transcripts=transcripts.get_transcripts(services, artifact_id)
    )


@router.post("/artifacts/{artifact_id}/transcripts", response_model=TranscriptInfo, status_code=201)
def create_transcript(
    services: Services, artifact_id: str, request: TranscriptCreateRequest
) -> TranscriptInfo:
    """Transcribe the artifact's audio locally (Pass 1). For a video, the audio track is extracted
    with ffmpeg and kept as a derived file so the lineage is explicit; the original is only read.
    409 with a clear reason when transcription is off or the runtime is not installed."""
    return transcripts.create_transcript(services, artifact_id, request.language)


@router.patch("/artifacts/{artifact_id}/transcripts/{transcript_id}", response_model=TranscriptInfo)
def update_transcript(
    services: Services, artifact_id: str, transcript_id: str, update: TranscriptUpdate
) -> TranscriptInfo:
    """Store the analyst's correction beside the model's text, or set the review state. Recorded as
    a custody event naming the changed fields, never the text."""
    return transcripts.update_transcript(services, artifact_id, transcript_id, update)


@router.delete("/artifacts/{artifact_id}/transcripts/{transcript_id}", status_code=204)
def delete_transcript(services: Services, artifact_id: str, transcript_id: str) -> None:
    """Delete a transcript. The extracted audio remains a derived file of its analysis."""
    transcripts.delete_transcript(services, artifact_id, transcript_id)


@router.post("/artifacts/{artifact_id}/index", response_model=IndexResult)
def index_artifact(services: Services, artifact_id: str) -> IndexResult:
    """Build this artifact's local semantic index from the analyst's own held text (Pass 1): notes,
    OCR output, transcripts, selected metadata, leads, and location candidates. Replaces any
    earlier index; nothing leaves this machine."""
    return semantic.index_artifact(services, artifact_id)


@router.delete("/artifacts/{artifact_id}/index", response_model=IndexResult)
def clear_artifact_index(services: Services, artifact_id: str) -> IndexResult:
    """Drop this artifact's index. It is derived data and can be rebuilt at any time."""
    return semantic.clear_index(services, artifact_id)


@router.get("/search", response_model=SearchResponse)
def semantic_search(services: Services, q: str, limit: int = 20) -> SearchResponse:
    """Search the analyst's indexed material locally. Results are their own records, not findings."""
    return semantic.search(services, q, limit=min(max(limit, 1), 100))


@router.post("/answer", response_model=AnswerResponse)
def answer_question(services: Services, request: AnswerRequest) -> AnswerResponse:
    """Answer a question over the analyst's own material (Pass 1). The sources are always returned;
    a drafted answer is included only when a local generator is available, is labelled
    AI-generated and unverified, is never stored, and never becomes an evidence record."""
    return semantic.answer(services, request.question, request.artifact_ids)
