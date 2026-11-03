"""GET /artifacts: search, filters, sorting, pagination, and status indicators (M2 step 4)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core import ids
from app.core.container import AppServices
from app.core.logging import RedactQueryStrings
from app.models import AnalysisJob, Artifact, EvidenceRecord
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_runner import start_analysis

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def add_artifact(
    services: AppServices,
    filename: str,
    *,
    minutes: int = 0,
    size: int = 1000,
    state: str = "UNREVIEWED",
    notes: str = "",
    mime: str = "image/jpeg",
    in_library: bool = True,
) -> str:
    artifact_id = ids.new_id(ids.ARTIFACT)
    created = T0 + timedelta(minutes=minutes)
    with services.db.writer() as session, session.begin():
        session.add(
            Artifact(
                id=artifact_id,
                original_filename=filename,
                media_type="image",
                mime_type=mime,
                size_bytes=size,
                sha256=artifact_id[4:] + "0" * 32,
                md5=artifact_id[4:],
                width=10,
                height=10,
                stored_path=f"artifacts/{artifact_id}/original/{artifact_id}.jpg",
                review_state=state,
                analyst_notes=notes,
                review_updated_at=created,
                created_at=created,
                in_duplicate_library=in_library,
            )
        )
    return artifact_id


def add_job(
    services: AppServices,
    artifact_id: str,
    *,
    minutes: int,
    status: str = "completed",
    stages: dict[str, str] | None = None,
    matches: int | None = None,
    record_notes: str = "",
) -> str:
    """A finished job whose evidence records have the given stage statuses. `matches` adds a duplicates
    record with that many matches."""
    job_id = ids.new_id(ids.JOB)
    at = T0 + timedelta(minutes=minutes)
    stages = dict(stages or {"hashes": "succeeded"})
    if matches is not None:
        stages["duplicates"] = "succeeded"
    with services.db.writer() as session, session.begin():
        session.add(
            AnalysisJob(
                id=job_id,
                artifact_id=artifact_id,
                pipeline="image.v1",
                app_version="0.1.0",
                status=status,
                options={},
                created_at=at,
                started_at=at,
                completed_at=at,
            )
        )
        session.flush()
        for stage, stage_status in stages.items():
            payload: dict[str, Any] = {}
            if stage == "duplicates":
                payload = {"matches": [{"artifact_id": "x"}] * (matches or 0)}
            session.add(
                EvidenceRecord(
                    id=ids.new_id(ids.EVIDENCE),
                    artifact_id=artifact_id,
                    job_id=job_id,
                    stage=stage,
                    status=stage_status,
                    classification="DERIVED",
                    method="m",
                    source="s",
                    tool="t",
                    tool_version="1",
                    payload=payload,
                    errors=[],
                    limitations=["l"],
                    review_state="UNREVIEWED",
                    started_at=at,
                    completed_at=at,
                    analyst_notes=record_notes,
                )
            )
    return job_id


def listing(client: TestClient, **params: Any) -> dict:
    response = client.get("/api/v1/artifacts", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def names(client: TestClient, **params: Any) -> list[str]:
    return [item["filename"] for item in listing(client, **params)["items"]]


# --- Defaults and compatibility -----------------------------------------------------------------


def test_default_listing_is_newest_first_and_includes_archived(
    client: TestClient, services: AppServices
) -> None:
    add_artifact(services, "old.jpg", minutes=0)
    add_artifact(services, "archived.jpg", minutes=1, state="ARCHIVED")
    add_artifact(services, "new.jpg", minutes=2)

    body = listing(client)
    assert [i["filename"] for i in body["items"]] == ["new.jpg", "archived.jpg", "old.jpg"]
    assert (body["total"], body["limit"], body["offset"]) == (3, 50, 0)
    assert body["counts_by_review_state"] == {
        "UNREVIEWED": 2,
        "IN_REVIEW": 0,
        "REVIEWED": 0,
        "FLAGGED": 0,
        "ARCHIVED": 1,
    }


def test_archived_can_be_hidden_and_still_be_asked_for(client: TestClient, services: AppServices) -> None:
    add_artifact(services, "kept.jpg")
    add_artifact(services, "archived.jpg", state="ARCHIVED")

    assert names(client, include_archived="false") == ["kept.jpg"]
    assert names(client, include_archived="false", review_state="ARCHIVED") == ["archived.jpg"]
    # Counts still show how many are archived, for the "Show archived" control.
    assert listing(client, include_archived="false")["counts_by_review_state"]["ARCHIVED"] == 1


# --- Search -------------------------------------------------------------------------------------


def test_search_filename_is_unicode_case_insensitive(client: TestClient, services: AppServices) -> None:
    add_artifact(services, "Über-Hafen.JPG")
    add_artifact(services, "harbour.jpg")

    assert names(client, q="über-hafen") == ["Über-Hafen.JPG"]
    assert names(client, q="ÜBER") == ["Über-Hafen.JPG"]
    assert sorted(names(client, q="HA")) == ["harbour.jpg", "Über-Hafen.JPG"]


def test_search_treats_percent_and_underscore_literally(client: TestClient, services: AppServices) -> None:
    add_artifact(services, "50%_off.png")
    add_artifact(services, "50xoff.png")
    add_artifact(services, "plain.png")

    assert names(client, q="50%") == ["50%_off.png"]
    assert names(client, q="_") == ["50%_off.png"]
    assert names(client, q="%") == ["50%_off.png"]


def test_search_artifact_id_and_hash_prefixes(client: TestClient, services: AppServices) -> None:
    target = add_artifact(services, "target.jpg")
    add_artifact(services, "other.jpg")
    hex_part = target[4:]

    assert names(client, q=target) == ["target.jpg"]
    assert names(client, q=hex_part[:12]) == ["target.jpg"]  # ID substring, SHA-256 and MD5 prefix
    assert names(client, q=hex_part[:8].upper()) == ["target.jpg"]


def test_search_artifact_and_record_notes(client: TestClient, services: AppServices) -> None:
    add_artifact(services, "a.jpg", notes="Source: Harbour Authority press office")
    noted = add_artifact(services, "b.jpg")
    add_job(services, noted, minutes=1, record_notes="EXIF date contradicts the caption")
    add_artifact(services, "c.jpg")

    assert names(client, q="harbour authority") == ["a.jpg"]
    assert names(client, q="CONTRADICTS") == ["b.jpg"]


def test_blank_search_is_ignored(client: TestClient, services: AppServices) -> None:
    add_artifact(services, "a.jpg")
    assert names(client, q="   ") == ["a.jpg"]


# --- Filters ------------------------------------------------------------------------------------


def test_filter_by_review_state(client: TestClient, services: AppServices) -> None:
    add_artifact(services, "u.jpg", state="UNREVIEWED")
    add_artifact(services, "f.jpg", state="FLAGGED")
    add_artifact(services, "r.jpg", state="REVIEWED")

    assert sorted(names(client, review_state=["FLAGGED", "REVIEWED"])) == ["f.jpg", "r.jpg"]
    counts = listing(client, review_state="FLAGGED")["counts_by_review_state"]
    assert counts["UNREVIEWED"] == counts["FLAGGED"] == counts["REVIEWED"] == 1


def test_filter_by_analysis_status(client: TestClient, services: AppServices) -> None:
    never = add_artifact(services, "never.jpg")
    done = add_artifact(services, "done.jpg")
    add_job(services, done, minutes=1)
    rerun = add_artifact(services, "rerun.jpg")
    add_job(services, rerun, minutes=1, status="completed")
    add_job(services, rerun, minutes=2, status="failed")
    assert never

    assert names(client, analysis_status="not_analysed") == ["never.jpg"]
    assert names(client, analysis_status="completed") == ["done.jpg"]
    assert sorted(names(client, analysis_status=["failed", "not_analysed"])) == ["never.jpg", "rerun.jpg"]


def test_filter_by_problems_and_duplicates(client: TestClient, services: AppServices) -> None:
    clean = add_artifact(services, "clean.jpg")
    add_job(services, clean, minutes=1, matches=0)
    partial = add_artifact(services, "partial.jpg")
    add_job(services, partial, minutes=1, stages={"hashes": "succeeded", "metadata": "partial"}, matches=2)
    add_artifact(services, "never.jpg")

    assert names(client, has_problems="true") == ["partial.jpg"]
    assert sorted(names(client, has_problems="false")) == ["clean.jpg", "never.jpg"]
    assert names(client, has_duplicates="true") == ["partial.jpg"]


def test_filter_by_type_and_upload_dates(client: TestClient, services: AppServices) -> None:
    add_artifact(services, "a.png", minutes=0, mime="image/png")
    add_artifact(services, "b.jpg", minutes=60)
    add_artifact(services, "c.jpg", minutes=120)

    assert names(client, mime_type="image/png") == ["a.png"]
    window = {
        "uploaded_from": (T0 + timedelta(minutes=60)).isoformat(),
        "uploaded_to": (T0 + timedelta(minutes=120)).isoformat(),
    }
    assert names(client, **window) == ["c.jpg", "b.jpg"]  # both ends inclusive


# --- Sorting and pagination ---------------------------------------------------------------------


def test_sort_by_filename_is_case_insensitive(client: TestClient, services: AppServices) -> None:
    for i, name in enumerate(["beta.jpg", "Alpha.jpg", "gamma.jpg", "alpha2.jpg"]):
        add_artifact(services, name, minutes=i)

    assert names(client, sort="filename", order="asc") == ["Alpha.jpg", "alpha2.jpg", "beta.jpg", "gamma.jpg"]
    assert names(client, sort="filename", order="desc") == [
        "gamma.jpg",
        "beta.jpg",
        "alpha2.jpg",
        "Alpha.jpg",
    ]


def test_sort_by_size_with_stable_ties(client: TestClient, services: AppServices) -> None:
    add_artifact(services, "small.jpg", size=10, minutes=0)
    add_artifact(services, "tie-old.jpg", size=50, minutes=1)
    add_artifact(services, "tie-new.jpg", size=50, minutes=2)
    add_artifact(services, "big.jpg", size=90, minutes=3)

    assert names(client, sort="size_bytes", order="asc") == [
        "small.jpg",
        "tie-new.jpg",
        "tie-old.jpg",
        "big.jpg",
    ]
    assert names(client, sort="size_bytes", order="desc") == [
        "big.jpg",
        "tie-new.jpg",
        "tie-old.jpg",
        "small.jpg",
    ]


def test_sort_by_review_state_follows_the_evidence_model_order(
    client: TestClient, services: AppServices
) -> None:
    for i, state in enumerate(["ARCHIVED", "FLAGGED", "REVIEWED", "IN_REVIEW", "UNREVIEWED"]):
        add_artifact(services, f"{state.lower()}.jpg", state=state, minutes=i)

    assert names(client, sort="review_state", order="asc") == [
        "unreviewed.jpg",
        "in_review.jpg",
        "reviewed.jpg",
        "flagged.jpg",
        "archived.jpg",
    ]


def test_sort_by_upload_date_ascending(client: TestClient, services: AppServices) -> None:
    add_artifact(services, "second.jpg", minutes=1)
    add_artifact(services, "first.jpg", minutes=0)
    assert names(client, sort="created_at", order="asc") == ["first.jpg", "second.jpg"]


def test_pagination(client: TestClient, services: AppServices) -> None:
    for i in range(5):
        add_artifact(services, f"{i}.jpg", minutes=i)

    page = listing(client, limit=2, offset=2)
    assert [i["filename"] for i in page["items"]] == ["2.jpg", "1.jpg"]
    assert (page["total"], page["limit"], page["offset"]) == (5, 2, 2)
    assert listing(client, limit=2, offset=10)["items"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"bogus": "1"},
        {"sort": "sha256"},
        {"order": "sideways"},
        {"limit": "0"},
        {"limit": "201"},
        {"offset": "-1"},
        {"review_state": "FAKE"},
        {"analysis_status": "done"},
        {"mime_type": "image/gif"},
        {"has_problems": "maybe"},
        {"uploaded_from": "2026-11-01"},  # a timezone is required
        {"uploaded_from": "2026-11-02T00:00:00Z", "uploaded_to": "2026-11-01T00:00:00Z"},
        {"q": "x" * 201},
    ],
)
def test_invalid_parameters_are_rejected(client: TestClient, params: dict) -> None:
    body = assert_error(client.get("/api/v1/artifacts", params=params), 422, "VALIDATION_ERROR")
    assert "x" * 201 not in str(body)  # submitted values are not echoed


# --- Indicators ---------------------------------------------------------------------------------


def item_for(client: TestClient, artifact_id: str) -> dict:
    return next(i for i in listing(client)["items"] if i["artifact_id"] == artifact_id)


def test_indicators_for_an_artifact_never_analysed(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "new.jpg")
    item = item_for(client, artifact_id)
    assert item["latest_job"] is None
    assert item["latest_job_status"] is None
    assert (item["problem_count"], item["duplicate_match_count"], item["added_since_analysis"]) == (
        None,
        None,
        None,
    )
    assert item["in_duplicate_library"] is True


def test_problem_count_uses_the_latest_job_only(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    add_job(
        services, artifact_id, minutes=1, stages={"metadata": "failed", "ocr": "partial", "c2pa": "failed"}
    )
    job_id = add_job(
        services, artifact_id, minutes=2, status="failed", stages={"hashes": "succeeded", "ocr": "partial"}
    )

    item = item_for(client, artifact_id)
    assert item["latest_job"]["job_id"] == job_id
    assert item["problem_count"] == 2  # one partial stage + the failed job


def test_duplicate_indicators(client: TestClient, services: AppServices) -> None:
    searched = add_artifact(services, "searched.jpg", minutes=0)
    add_job(services, searched, minutes=10, matches=3)
    add_artifact(services, "before-search.jpg", minutes=5)
    add_artifact(services, "after-search.jpg", minutes=20)
    add_artifact(services, "after-but-excluded.jpg", minutes=21, in_library=False)
    skipped = add_artifact(services, "no-search.jpg", minutes=22)
    add_job(services, skipped, minutes=23, stages={"hashes": "succeeded", "duplicates": "skipped"})

    item = item_for(client, searched)
    assert item["duplicate_match_count"] == 3
    assert item["added_since_analysis"] == 2  # after-search.jpg and no-search.jpg
    skipped_item = item_for(client, skipped)
    assert (skipped_item["duplicate_match_count"], skipped_item["added_since_analysis"]) == (None, None)


def test_detail_has_the_same_indicators(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    add_job(services, artifact_id, minutes=1, stages={"ocr": "failed"}, matches=1)

    detail = client.get(f"/api/v1/artifacts/{artifact_id}").json()
    assert (detail["problem_count"], detail["duplicate_match_count"], detail["added_since_analysis"]) == (
        1,
        1,
        0,
    )
    assert detail["in_duplicate_library"] is True
    assert detail["latest_job"]["status"] == "completed"


def test_indicators_from_real_analyses(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    original = upload_ok(client, fixtures.jpeg)["artifact_id"]
    start_analysis(client, original)
    copy = upload_ok(client, fixtures.near_duplicate)["artifact_id"]

    first = item_for(client, original)
    assert (first["problem_count"], first["duplicate_match_count"], first["added_since_analysis"]) == (
        0,
        0,
        1,
    )
    assert item_for(client, copy)["latest_job"] is None

    start_analysis(client, copy)
    second = item_for(client, copy)
    assert (second["problem_count"], second["duplicate_match_count"], second["added_since_analysis"]) == (
        0,
        1,
        0,
    )
    assert names(client, has_duplicates="true") == [fixtures.near_duplicate.name]


# --- Logging ------------------------------------------------------------------------------------


def test_access_log_redacts_query_strings(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    access = logging.getLogger("uvicorn.access")
    assert any(isinstance(f, RedactQueryStrings) for f in access.filters)
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", "/api/v1/artifacts?q=secret+source+name", "1.1", 200),
        None,
    )
    assert access.filters[-1].filter(record)
    message = record.getMessage()
    assert "secret" not in message
    assert "/api/v1/artifacts?[query redacted]" in message
