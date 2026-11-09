"""Local semantic search and retrieval (Pass 1, D24).

Indexes only the analyst's own held text — notes, OCR output, transcripts, selected metadata, and
their own leads and location candidates — into vectors stored beside the artifact. Everything stays
on this machine: no text, vector, or question is ever sent anywhere.

Retrieval returns the analyst's own material. When a local generator is available, a drafted answer
may accompany it, but the sources are always returned and the answer is always labelled
AI-generated and unverified. An answer is never stored, never becomes an evidence record, and never
stands on its own.
"""

import logging
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.models import Artifact, EmbeddingChunk, EvidenceRecord, ExternalLead, LocationCandidate, Transcript
from app.schemas.common import ErrorCode
from app.schemas.semantic import (
    AnswerResponse,
    IndexResult,
    SearchHit,
    SearchResponse,
)
from app.services import ai, app_settings, custody
from app.services.ai_drafts import _latest_record, _metadata_lines
from app.services.errors import artifact_not_found

logger = get_logger("semantic")

EMBEDDINGS_INDEXED = "embeddings_indexed"
EMBEDDINGS_CLEARED = "embeddings_cleared"

# Chunking: small enough that a hit points at something specific, large enough to carry context.
CHUNK_CHARACTERS = 600
CHUNK_OVERLAP = 80
MAX_CHUNKS_PER_ARTIFACT = 400

# Vestigo drafts no answers. The local runtime has no free-text generation at all: its `complete()`
# call with no tools returns an empty call, and this was verified rather than assumed (D27). So
# `answer` retrieves and returns the analyst's own material, and says that is what it did.
NO_GENERATOR_NOTE = (
    "No local text-generation model exists in this runtime, so Vestigo returned the matching "
    "material itself rather than drafting an answer. These are your own records, unaltered."
)

_WHITESPACE = re.compile(r"\s+")


def _chunk(text: str) -> list[str]:
    clean = _WHITESPACE.sub(" ", text).strip()
    if not clean:
        return []
    if len(clean) <= CHUNK_CHARACTERS:
        return [clean]
    chunks: list[str] = []
    start = 0
    while start < len(clean) and len(chunks) < MAX_CHUNKS_PER_ARTIFACT:
        end = min(start + CHUNK_CHARACTERS, len(clean))
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _collect_text(session: Session, artifact: Artifact) -> list[tuple[str, str | None, str]]:
    """(source_kind, source_ref, text) for everything of the analyst's that is worth indexing."""
    pieces: list[tuple[str, str | None, str]] = []
    if artifact.analyst_notes:
        pieces.append(("analyst_notes", None, artifact.analyst_notes))

    for stage in ("ocr", "keyframe_ocr"):
        record = _latest_record(session, artifact.id, stage)
        if record is None:
            continue
        payload = record.payload or {}
        if stage == "ocr":
            text = str(payload.get("cleaned_text") or payload.get("text") or "")
        else:
            text = "\n".join(
                str(frame.get("cleaned_text") or frame.get("text") or "")
                for frame in payload.get("frames") or []
                if isinstance(frame, dict)
            )
        if text.strip():
            pieces.append(("ocr_text", record.id, text))

    metadata = _latest_record(session, artifact.id, "metadata")
    if metadata is not None:
        lines = _metadata_lines(metadata.payload or {})
        if lines:
            pieces.append(("metadata", metadata.id, "\n".join(lines)))

    for transcript in session.scalars(select(Transcript).where(Transcript.artifact_id == artifact.id)):
        text = transcript.edited_text or transcript.text
        if text.strip():
            pieces.append(("transcript", transcript.id, text))

    for candidate in session.scalars(
        select(LocationCandidate).where(LocationCandidate.artifact_id == artifact.id)
    ):
        pieces.append(
            (
                "location_candidate",
                candidate.id,
                f"{candidate.description}. {candidate.basis} {candidate.notes}".strip(),
            )
        )

    for lead in session.scalars(select(ExternalLead).where(ExternalLead.artifact_id == artifact.id)):
        text = f"{lead.provider} {lead.result_url} {lead.notes}".strip()
        pieces.append(("external_lead", lead.id, text))

    # Analyst notes on individual evidence records are theirs too.
    for record in session.scalars(
        select(EvidenceRecord).where(
            EvidenceRecord.artifact_id == artifact.id, EvidenceRecord.analyst_notes != ""
        )
    ):
        pieces.append(("record_notes", record.id, record.analyst_notes))
    return pieces


def _get_artifact(session: Session, artifact_id: str) -> Artifact:
    artifact = session.get(Artifact, artifact_id) if ids.is_valid_id(artifact_id, ids.ARTIFACT) else None
    if artifact is None:
        raise artifact_not_found(artifact_id)
    return artifact


def _embedder(services: AppServices):
    editable = app_settings.get_settings_response(services).editable
    embedder = ai.resolve_embedder(enabled=editable.semantic_search_enabled)
    reason = ai.unavailable_reason(embedder)
    if reason is not None:
        raise AppError(409, ErrorCode.AI_UNAVAILABLE, reason, {})
    return embedder


def index_artifact(services: AppServices, artifact_id: str) -> IndexResult:
    """Rebuild this artifact's index from its current held text. Replaces any earlier index."""
    embedder = _embedder(services)
    with services.db.reader() as session:
        artifact = _get_artifact(session, artifact_id)
        pieces = _collect_text(session, artifact)

    rows: list[dict] = []
    for source_kind, source_ref, text in pieces:
        for ordinal, chunk in enumerate(_chunk(text)):
            rows.append(
                {"source_kind": source_kind, "source_ref": source_ref, "ordinal": ordinal, "text": chunk}
            )
    rows = rows[:MAX_CHUNKS_PER_ARTIFACT]

    vectors = embedder.embed([row["text"] for row in rows]) if rows else None
    now = utcnow()
    with services.db.writer() as session, session.begin():
        session.execute(delete(EmbeddingChunk).where(EmbeddingChunk.artifact_id == artifact_id))
        for row, vector in zip(rows, vectors.vectors if vectors else [], strict=True):
            session.add(
                EmbeddingChunk(
                    id=ids.new_id(ids.EMBEDDING_CHUNK),
                    artifact_id=artifact_id,
                    source_kind=row["source_kind"],
                    source_ref=row["source_ref"],
                    ordinal=row["ordinal"],
                    text=row["text"],
                    vector=vector,
                    model_name=vectors.model.name if vectors else "",
                    dimensions=embedder.dimensions,
                    created_at=now,
                )
            )
        custody.record_event(
            session,
            artifact_id,
            EMBEDDINGS_INDEXED,
            {
                "chunks": len(rows),
                "model": vectors.model.name if vectors else None,
                "sources": sorted({row["source_kind"] for row in rows}),
            },
        )
    log_event(logger, logging.INFO, "semantic.indexed", artifact_id=artifact_id, count=len(rows))
    return IndexResult(
        artifact_id=artifact_id,
        chunks=len(rows),
        model=vectors.model.name if vectors else None,
        sources=sorted({row["source_kind"] for row in rows}),
    )


def clear_index(services: AppServices, artifact_id: str) -> IndexResult:
    with services.db.writer() as session, session.begin():
        _get_artifact(session, artifact_id)
        removed = session.execute(
            delete(EmbeddingChunk).where(EmbeddingChunk.artifact_id == artifact_id)
        ).rowcount
        custody.record_event(session, artifact_id, EMBEDDINGS_CLEARED, {"chunks": int(removed or 0)})
    return IndexResult(artifact_id=artifact_id, chunks=0, model=None, sources=[])


def search(services: AppServices, query: str, limit: int = 20) -> SearchResponse:
    """Rank the analyst's indexed chunks against the query. Local, lexical-to-semantic per model."""
    embedder = _embedder(services)
    vector = embedder.embed([query]).vectors[0]
    with services.db.reader() as session:
        rows = list(
            session.execute(
                select(EmbeddingChunk, Artifact.original_filename, Artifact.media_type).join(
                    Artifact, Artifact.id == EmbeddingChunk.artifact_id
                )
            ).all()
        )
    model_name = embedder.embed([""]).model.name
    scored: list[SearchHit] = []
    for chunk, filename, media_type in rows:
        if chunk.dimensions != embedder.dimensions or chunk.model_name != model_name:
            # Never mix indexes from different models or dimensions; say so instead.
            continue
        score = ai.cosine(vector, list(chunk.vector or []))
        if score <= 0.0:
            continue
        scored.append(
            SearchHit(
                artifact_id=chunk.artifact_id,
                filename=filename,
                media_type=media_type,
                source_kind=chunk.source_kind,
                source_ref=chunk.source_ref,
                score=round(score, 4),
                text=chunk.text,
            )
        )
    scored.sort(key=lambda hit: hit.score, reverse=True)
    return SearchResponse(query=query, hits=scored[:limit], model=model_name)


def answer(
    services: AppServices, question: str, artifact_ids: list[str] | None, limit: int = 8
) -> AnswerResponse:
    """Retrieve the analyst's own material for a question. Nothing is drafted and nothing is invented."""
    found = search(services, question, limit=limit * 3)
    hits = [hit for hit in found.hits if not artifact_ids or hit.artifact_id in set(artifact_ids)]
    hits = hits[:limit]
    return AnswerResponse(
        question=question,
        # The sources are the answer. `answer` stays None because no local model can write one.
        sources=hits,
        answer=None,
        notice=NO_GENERATOR_NOTE,
        label=ai.AI_LABEL,
    )
