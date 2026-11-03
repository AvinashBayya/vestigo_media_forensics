"""The artifact Library: search, filters, sorting, and status indicators (Milestone 2, step 4).

Status indicators describe each artifact's latest analysis job:

- `problem_count`: stages that failed or were partial, plus one if the job itself failed. None if the
  artifact has never been analysed.
- `duplicate_match_count`: matches in the latest job's duplicate search. None if that search did not
  produce a result (not run, skipped, or failed).
- `added_since_analysis`: artifacts in the duplicate library that were uploaded after that search
  finished, so it could not have compared them. None if there is no duplicate-search result.
"""

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core import ids
from app.models import AnalysisJob, Artifact, DerivedFile, EvidenceRecord, ImageFingerprint
from app.schemas.analysis import JobSummary
from app.schemas.artifact import (
    AnalysisStatusFilter,
    ArtifactListItem,
    ArtifactQuery,
    ArtifactSort,
    SortOrder,
)
from app.schemas.common import JobStatus, MediaType, ReviewState, StageStatus
from app.schemas.library import LibraryArtifactRef, LibrarySummary, StorageUsage
from app.services.phash import FINGERPRINT_ALGORITHM

PROBLEM_STATUSES = (StageStatus.FAILED, StageStatus.PARTIAL)
RESULT_STATUSES = (StageStatus.SUCCEEDED, StageStatus.PARTIAL)
# 04-EVIDENCE-MODEL.md §4 order.
REVIEW_STATE_ORDER = list(ReviewState)
HEX_PREFIX = re.compile(r"[0-9a-f]{8,64}")


def _latest_jobs() -> Any:
    ranked = select(
        AnalysisJob.id.label("job_id"),
        AnalysisJob.artifact_id.label("artifact_id"),
        AnalysisJob.status.label("job_status"),
        func.row_number()
        .over(
            partition_by=AnalysisJob.artifact_id,
            order_by=(AnalysisJob.created_at.desc(), AnalysisJob.id.desc()),
        )
        .label("rank"),
    ).subquery("ranked_jobs")
    return (
        select(ranked.c.job_id, ranked.c.artifact_id, ranked.c.job_status)
        .where(ranked.c.rank == 1)
        .subquery("latest_job")
    )


def _job_stats() -> Any:
    duplicates_result = and_(EvidenceRecord.stage == "duplicates", EvidenceRecord.status.in_(RESULT_STATUSES))
    return (
        select(
            EvidenceRecord.job_id.label("job_id"),
            func.sum(case((EvidenceRecord.status.in_(PROBLEM_STATUSES), 1), else_=0)).label("problems"),
            func.max(
                case((duplicates_result, func.json_array_length(EvidenceRecord.payload, "$.matches")))
            ).label("duplicate_matches"),
            func.max(case((duplicates_result, EvidenceRecord.completed_at))).label("searched_at"),
        )
        .group_by(EvidenceRecord.job_id)
        .subquery("job_stats")
    )


@dataclass(frozen=True)
class _Columns:
    latest: Any
    stats: Any
    problem_count: ColumnElement[Any]
    duplicate_match_count: ColumnElement[Any]
    added_since_analysis: ColumnElement[Any]


def _columns() -> _Columns:
    latest, stats = _latest_jobs(), _job_stats()
    problem_count = case(
        (latest.c.job_id.is_(None), None),
        else_=func.coalesce(stats.c.problems, 0)
        + case((latest.c.job_status == JobStatus.FAILED, 1), else_=0),
    )
    other = aliased(Artifact)
    added = (
        select(func.count())
        .where(
            other.in_duplicate_library.is_(True),
            other.id != Artifact.id,
            other.created_at > stats.c.searched_at,
        )
        .scalar_subquery()
    )
    added_since = case((stats.c.searched_at.is_(None), None), else_=added)
    return _Columns(latest, stats, problem_count, stats.c.duplicate_matches, added_since)


def _base(columns: _Columns) -> Select[Any]:
    return (
        select(
            Artifact,
            columns.latest.c.job_id,
            columns.problem_count.label("problem_count"),
            columns.duplicate_match_count.label("duplicate_match_count"),
            columns.added_since_analysis.label("added_since_analysis"),
        )
        .outerjoin(columns.latest, columns.latest.c.artifact_id == Artifact.id)
        .outerjoin(columns.stats, columns.stats.c.job_id == columns.latest.c.job_id)
    )


def _search(q: str) -> ColumnElement[bool]:
    """Filename, artifact ID, SHA-256/MD5 prefix, or analyst notes (artifact or evidence record).

    Matching is a plain, Unicode case-insensitive substring test, so `%` and `_` are literal.
    """
    needle = q.casefold()
    conditions: list[ColumnElement[bool]] = [
        func.instr(func.vestigo_casefold(Artifact.original_filename), needle) > 0,
        func.instr(func.vestigo_casefold(Artifact.analyst_notes), needle) > 0,
        exists().where(
            EvidenceRecord.artifact_id == Artifact.id,
            func.instr(func.vestigo_casefold(EvidenceRecord.analyst_notes), needle) > 0,
        ),
    ]
    # IDs are matched only for ID-like terms, so that e.g. "_" does not match every "art_" ID.
    if needle.startswith(f"{ids.ARTIFACT}_") or HEX_PREFIX.fullmatch(needle):
        conditions.append(func.instr(Artifact.id, needle) > 0)
    if HEX_PREFIX.fullmatch(needle):
        conditions.append(func.substr(Artifact.sha256, 1, len(needle)) == needle)
        if len(needle) <= 32:
            conditions.append(func.substr(Artifact.md5, 1, len(needle)) == needle)
    return or_(*conditions)


def _filters(query: ArtifactQuery, columns: _Columns, *, facet: bool = False) -> list[ColumnElement[bool]]:
    """WHERE conditions. With `facet`, the review-state and archive filters are left out, so counts by
    review state show what each review-state choice would return."""
    conditions: list[ColumnElement[bool]] = []
    if query.q:
        conditions.append(_search(query.q))
    if not facet:
        if query.review_state:
            conditions.append(Artifact.review_state.in_(query.review_state))
        if not query.include_archived and ReviewState.ARCHIVED not in query.review_state:
            conditions.append(Artifact.review_state != ReviewState.ARCHIVED)
    if query.analysis_status:
        statuses = [s.value for s in query.analysis_status if s != AnalysisStatusFilter.NOT_ANALYSED]
        options = [columns.latest.c.job_status.in_(statuses)] if statuses else []
        if AnalysisStatusFilter.NOT_ANALYSED in query.analysis_status:
            options.append(columns.latest.c.job_id.is_(None))
        conditions.append(or_(*options))
    if query.has_problems is not None:
        problems = func.coalesce(columns.problem_count, 0)
        conditions.append(problems > 0 if query.has_problems else problems == 0)
    if query.has_duplicates is not None:
        matches = func.coalesce(columns.duplicate_match_count, 0)
        conditions.append(matches > 0 if query.has_duplicates else matches == 0)
    if query.mime_type:
        conditions.append(Artifact.mime_type.in_(query.mime_type))
    if query.uploaded_from is not None:
        conditions.append(Artifact.created_at >= query.uploaded_from)
    if query.uploaded_to is not None:
        conditions.append(Artifact.created_at <= query.uploaded_to)
    return conditions


def _order_by(query: ArtifactQuery) -> list[ColumnElement[Any]]:
    descending = query.order == SortOrder.DESC
    if query.sort == ArtifactSort.CREATED_AT:
        keys: list[ColumnElement[Any]] = [Artifact.created_at, Artifact.id]
        return [key.desc() if descending else key.asc() for key in keys]
    primary: ColumnElement[Any] = {
        ArtifactSort.FILENAME: Artifact.original_filename.collate("NOCASE"),
        ArtifactSort.SIZE_BYTES: Artifact.size_bytes,
        ArtifactSort.REVIEW_STATE: case(
            {state.value: rank for rank, state in enumerate(REVIEW_STATE_ORDER)}, value=Artifact.review_state
        ),
    }[query.sort]
    # Ties: newest upload first, then ID, whatever the direction, so pages are stable.
    return [primary.desc() if descending else primary.asc(), Artifact.created_at.desc(), Artifact.id.desc()]


@dataclass(frozen=True)
class LibraryPage:
    items: list[ArtifactListItem]
    total: int
    counts_by_review_state: dict[ReviewState, int]


def _to_items(session: Session, rows: list[Any]) -> list[ArtifactListItem]:
    job_ids = [row.job_id for row in rows if row.job_id]
    jobs = (
        {job.id: job for job in session.scalars(select(AnalysisJob).where(AnalysisJob.id.in_(job_ids)))}
        if job_ids
        else {}
    )
    items = []
    for row in rows:
        artifact: Artifact = row.Artifact
        job = jobs.get(row.job_id) if row.job_id else None
        items.append(
            ArtifactListItem(
                artifact_id=artifact.id,
                filename=artifact.original_filename,
                media_type=MediaType(artifact.media_type),
                mime_type=artifact.mime_type,
                size_bytes=artifact.size_bytes,
                created_at=artifact.created_at,
                review_state=ReviewState(artifact.review_state),
                latest_job_status=JobStatus(job.status) if job else None,
                latest_job=JobSummary(
                    job_id=job.id,
                    status=JobStatus(job.status),
                    created_at=job.created_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                )
                if job
                else None,
                problem_count=row.problem_count,
                duplicate_match_count=row.duplicate_match_count,
                added_since_analysis=row.added_since_analysis,
                in_duplicate_library=artifact.in_duplicate_library,
            )
        )
    return items


def list_artifacts(session: Session, query: ArtifactQuery) -> LibraryPage:
    columns = _columns()
    filtered = _base(columns).where(*_filters(query, columns))
    total = session.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    rows = session.execute(filtered.order_by(*_order_by(query)).limit(query.limit).offset(query.offset)).all()

    facet = _base(columns).where(*_filters(query, columns, facet=True)).subquery()
    by_state = select(facet.c.review_state, func.count()).group_by(facet.c.review_state)
    counts = dict(session.execute(by_state).all())
    return LibraryPage(
        items=_to_items(session, list(rows)),
        total=total,
        counts_by_review_state={state: counts.get(state.value, 0) for state in ReviewState},
    )


def list_item(session: Session, artifact_id: str) -> ArtifactListItem | None:
    """One artifact with the same indicators as the Library."""
    columns = _columns()
    rows = session.execute(_base(columns).where(Artifact.id == artifact_id)).all()
    items = _to_items(session, list(rows))
    return items[0] if items else None


SUMMARY_LIST_LIMIT = 100


def set_duplicate_library(session: Session, artifact: Artifact, included: bool) -> None:
    """Include or exclude an artifact from future duplicate searches. Recorded evidence is untouched."""
    artifact.in_duplicate_library = included


def library_summary(session: Session) -> LibrarySummary:
    indexed = exists().where(
        ImageFingerprint.artifact_id == Artifact.id, ImageFingerprint.algorithm == FINGERPRINT_ALGORITHM
    )
    newest = (Artifact.created_at.desc(), Artifact.id.desc())

    def refs(*conditions: ColumnElement[bool]) -> list[LibraryArtifactRef]:
        rows = session.execute(
            select(Artifact.id, Artifact.original_filename, Artifact.created_at, indexed.label("indexed"))
            .where(*conditions)
            .order_by(*newest)
            .limit(SUMMARY_LIST_LIMIT)
        ).all()
        return [
            LibraryArtifactRef(artifact_id=a, filename=f, created_at=c, indexed=bool(i))
            for a, f, c, i in rows
        ]

    def count(*conditions: ColumnElement[bool]) -> int:
        return session.scalar(select(func.count()).select_from(Artifact).where(*conditions)) or 0

    included = Artifact.in_duplicate_library.is_(True)
    return LibrarySummary(
        artifact_count=count(),
        indexed_count=count(included, indexed),
        not_indexed_count=count(included, ~indexed),
        excluded_count=count(~included),
        not_indexed=refs(included, ~indexed),
        excluded=refs(~included),
        storage=StorageUsage(
            original_bytes=session.scalar(select(func.coalesce(func.sum(Artifact.size_bytes), 0))) or 0,
            derived_bytes=session.scalar(select(func.coalesce(func.sum(DerivedFile.size_bytes), 0))) or 0,
        ),
    )
