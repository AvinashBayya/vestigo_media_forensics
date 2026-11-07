"""Semantic search and retrieval schemas (Pass 1, D24)."""

from pydantic import BaseModel, ConfigDict, Field


class IndexResult(BaseModel):
    artifact_id: str
    chunks: int
    # The model that produced the vectors; indexes are never mixed across models.
    model: str | None
    sources: list[str] = []


class SearchHit(BaseModel):
    """One piece of the analyst's own held text that matched. Not a finding, just a pointer."""

    artifact_id: str
    filename: str | None
    media_type: str | None
    source_kind: str
    source_ref: str | None
    score: float
    text: str


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    model: str | None = None


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    # Limit retrieval to these artifacts, or omit to search the whole local library.
    artifact_ids: list[str] | None = None


class AnswerResponse(BaseModel):
    question: str
    # Always present: the analyst's own material the answer was drawn from.
    sources: list[SearchHit]
    # Absent when no local generator is available; the sources are returned regardless.
    answer: str | None
    notice: str
    label: str
