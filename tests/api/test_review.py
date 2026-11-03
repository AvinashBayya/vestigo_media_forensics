"""Review workflow: artifact review, conflicts, bulk review, record review, and history (M2 step 6)."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DatabaseError

from app.core.container import AppServices
from app.models import Artifact, EvidenceRecord, ReviewEvent
from tests.api.test_library import add_artifact, add_job
from tests.helpers import assert_error

LONG_NOTE = "Source checked with the harbour authority.\n" + "Line two — ünïcode ✓. " * 200


def events(services: AppServices, artifact_id: str) -> list[ReviewEvent]:
    with services.db.reader() as session:
        return list(
            session.scalars(
                select(ReviewEvent)
                .where(ReviewEvent.artifact_id == artifact_id)
                .order_by(ReviewEvent.created_at)
            )
        )


def review(client: TestClient, artifact_id: str, **body: object):
    return client.patch(f"/api/v1/artifacts/{artifact_id}/review", json=body)


def record_ids(services: AppServices, artifact_id: str) -> dict[str, str]:
    with services.db.reader() as session:
        return dict(
            session.execute(
                select(EvidenceRecord.stage, EvidenceRecord.id).where(
                    EvidenceRecord.artifact_id == artifact_id
                )
            ).all()
        )


def record_review(client: TestClient, artifact_id: str, evidence_id: str, **body: object):
    return client.patch(f"/api/v1/artifacts/{artifact_id}/evidence/{evidence_id}/review", json=body)


# --- Artifact review ----------------------------------------------------------------------------


def test_artifact_review_change_writes_an_event_with_full_notes(
    client: TestClient, services: AppServices
) -> None:
    artifact_id = add_artifact(services, "a.jpg", notes="first note")

    response = review(client, artifact_id, state="FLAGGED", analyst_notes=LONG_NOTE)

    assert response.status_code == 200, response.text
    assert response.json()["review"]["state"] == "FLAGGED"
    assert response.json()["review"]["analyst_notes"] == LONG_NOTE
    [event] = events(services, artifact_id)
    assert (event.origin, event.from_state, event.to_state, event.evidence_id) == (
        "artifact",
        "UNREVIEWED",
        "FLAGGED",
        None,
    )
    assert event.notes_before == "first note"
    assert event.notes_after == LONG_NOTE


def test_saving_without_a_change_writes_nothing(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    first = review(client, artifact_id, state="IN_REVIEW", analyst_notes="n").json()

    again = review(client, artifact_id, state="IN_REVIEW", analyst_notes="n").json()

    assert again["review"]["updated_at"] == first["review"]["updated_at"]
    assert len(events(services, artifact_id)) == 1


def test_stale_review_is_refused_with_the_current_values(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    seen = client.get(f"/api/v1/artifacts/{artifact_id}").json()["review"]["updated_at"]
    assert (
        review(
            client, artifact_id, state="IN_REVIEW", analyst_notes="from tab 1", expected_updated_at=seen
        ).status_code
        == 200
    )

    body = assert_error(
        review(client, artifact_id, state="REVIEWED", analyst_notes="from tab 2", expected_updated_at=seen),
        409,
        "REVIEW_CONFLICT",
    )

    current = body["details"]["current"]
    assert (current["state"], current["analyst_notes"]) == ("IN_REVIEW", "from tab 1")
    detail = client.get(f"/api/v1/artifacts/{artifact_id}").json()["review"]
    assert (detail["state"], detail["analyst_notes"]) == ("IN_REVIEW", "from tab 1")
    assert len(events(services, artifact_id)) == 1
    # Without expected_updated_at the Milestone 1 behaviour (last write wins) is kept.
    assert review(client, artifact_id, state="REVIEWED", analyst_notes="no check").status_code == 200


def test_review_validation(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    assert_error(review(client, artifact_id, state="AUTHENTIC"), 422, "VALIDATION_ERROR")
    assert_error(
        review(client, artifact_id, state="REVIEWED", analyst_notes="x" * 20_001), 422, "VALIDATION_ERROR"
    )
    assert_error(
        review(client, artifact_id, state="REVIEWED", expected_updated_at="yesterday"),
        422,
        "VALIDATION_ERROR",
    )


# --- Bulk review --------------------------------------------------------------------------------


def bulk(client: TestClient, artifact_ids: list[str], state: str = "REVIEWED"):
    return client.post("/api/v1/artifacts/review", json={"artifact_ids": artifact_ids, "state": state})


def test_bulk_review_updates_all_and_reports_unchanged(client: TestClient, services: AppServices) -> None:
    a = add_artifact(services, "a.jpg", notes="keep this note")
    b = add_artifact(services, "b.jpg", state="REVIEWED")
    c = add_artifact(services, "c.jpg", state="FLAGGED")

    response = bulk(client, [a, b, c, a])

    assert response.status_code == 200, response.text
    assert response.json() == {"state": "REVIEWED", "updated": [a, c], "unchanged": [b]}
    with services.db.reader() as session:
        states = dict(session.execute(select(Artifact.id, Artifact.review_state)).all())
        notes = session.get(Artifact, a).analyst_notes
    assert states == {a: "REVIEWED", b: "REVIEWED", c: "REVIEWED"}
    assert notes == "keep this note"
    [event] = events(services, a)
    assert (event.origin, event.from_state, event.to_state) == ("bulk", "UNREVIEWED", "REVIEWED")
    assert event.notes_before == event.notes_after == "keep this note"
    assert events(services, b) == []


def test_bulk_review_is_all_or_nothing(client: TestClient, services: AppServices) -> None:
    a = add_artifact(services, "a.jpg")
    gone = "art_" + "f" * 32

    body = assert_error(bulk(client, [a, gone, "not-an-id"]), 404, "ARTIFACT_NOT_FOUND")

    assert body["details"]["missing"] == sorted([gone, "not-an-id"])
    assert "Nothing was changed" in body["message"]
    with services.db.reader() as session:
        assert session.get(Artifact, a).review_state == "UNREVIEWED"
        assert session.scalar(select(func.count()).select_from(ReviewEvent)) == 0


def test_bulk_review_limits(client: TestClient, services: AppServices) -> None:
    a = add_artifact(services, "a.jpg")
    assert_error(bulk(client, []), 422, "VALIDATION_ERROR")
    assert_error(bulk(client, [a] * 201), 422, "VALIDATION_ERROR")
    assert_error(bulk(client, [a], state="FAKE"), 422, "VALIDATION_ERROR")
    ids_200 = [add_artifact(services, f"{i}.jpg") for i in range(199)] + [a]
    response = bulk(client, ids_200, state="ARCHIVED")
    assert response.status_code == 200
    assert len(response.json()["updated"]) == 200


# --- Record review ------------------------------------------------------------------------------


def test_record_review_is_separate_and_never_changes_classification(
    client: TestClient, services: AppServices
) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    add_job(services, artifact_id, minutes=1, stages={"hashes": "succeeded", "ocr": "succeeded"})
    ocr_id = record_ids(services, artifact_id)["ocr"]
    with services.db.reader() as session:
        before = session.get(EvidenceRecord, ocr_id)
        classification, payload = before.classification, before.payload

    response = record_review(
        client, artifact_id, ocr_id, state="FLAGGED", analyst_notes="OCR misread the date"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["review_state"], body["analyst_notes"], body["stage"]) == (
        "FLAGGED",
        "OCR misread the date",
        "ocr",
    )
    assert body["classification"] == classification
    assert body["review_updated_at"]
    with services.db.reader() as session:
        after = session.get(EvidenceRecord, ocr_id)
        assert (after.classification, after.payload) == (classification, payload)
        assert session.get(Artifact, artifact_id).review_state == "UNREVIEWED"  # artifact review untouched
    [event] = events(services, artifact_id)
    assert (event.origin, event.evidence_id, event.notes_before, event.notes_after) == (
        "record",
        ocr_id,
        "",
        "OCR misread the date",
    )

    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    provenance = report["ocr"]["provenance"]
    assert (provenance["review_state"], provenance["analyst_notes"]) == ("FLAGGED", "OCR misread the date")
    assert provenance["classification"] == classification
    assert report["hashes"]["provenance"]["review_state"] == "UNREVIEWED"


def test_record_review_conflicts(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    add_job(services, artifact_id, minutes=1)
    evidence_id = record_ids(services, artifact_id)["hashes"]

    # A never-reviewed record has no timestamp: null is the expected value.
    first = record_review(client, artifact_id, evidence_id, state="IN_REVIEW", expected_updated_at=None)
    assert first.status_code == 200
    body = assert_error(
        record_review(client, artifact_id, evidence_id, state="REVIEWED", expected_updated_at=None),
        409,
        "REVIEW_CONFLICT",
    )
    assert body["details"]["current"]["state"] == "IN_REVIEW"
    seen = first.json()["review_updated_at"]
    assert (
        record_review(
            client, artifact_id, evidence_id, state="REVIEWED", expected_updated_at=seen
        ).status_code
        == 200
    )


def test_record_review_not_found(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    other = add_artifact(services, "b.jpg")
    add_job(services, other, minutes=1)
    others_record = record_ids(services, other)["hashes"]

    assert_error(
        record_review(client, artifact_id, others_record, state="REVIEWED"), 404, "EVIDENCE_RECORD_NOT_FOUND"
    )
    assert_error(
        record_review(client, artifact_id, "ev_nope", state="REVIEWED"), 404, "EVIDENCE_RECORD_NOT_FOUND"
    )
    assert_error(
        record_review(client, "art_" + "0" * 32, others_record, state="REVIEWED"), 404, "ARTIFACT_NOT_FOUND"
    )


# --- History ------------------------------------------------------------------------------------


def test_history_lists_every_change_newest_first(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    job_id = add_job(services, artifact_id, minutes=1)
    evidence_id = record_ids(services, artifact_id)["hashes"]
    review(client, artifact_id, state="IN_REVIEW", analyst_notes="looking")
    record_review(client, artifact_id, evidence_id, state="REVIEWED", analyst_notes="hash matches")
    bulk(client, [artifact_id], state="FLAGGED")

    history = client.get(f"/api/v1/artifacts/{artifact_id}/review-history").json()

    assert history["artifact_id"] == artifact_id
    assert [(e["origin"], e["to_state"]) for e in history["events"]] == [
        ("bulk", "FLAGGED"),
        ("record", "REVIEWED"),
        ("artifact", "IN_REVIEW"),
    ]
    record_event = history["events"][1]
    assert (record_event["evidence_id"], record_event["stage"], record_event["job_id"]) == (
        evidence_id,
        "hashes",
        job_id,
    )
    assert history["events"][2]["notes_after"] == "looking"
    assert history["events"][2]["stage"] is None

    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    assert report["review_history"] == history["events"]
    assert_error(
        client.get(f"/api/v1/artifacts/{'art_' + '0' * 32}/review-history"), 404, "ARTIFACT_NOT_FOUND"
    )


def test_review_events_cannot_be_changed(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    review(client, artifact_id, state="IN_REVIEW", analyst_notes="original")

    with pytest.raises(DatabaseError, match="append-only"), services.db.writer() as session, session.begin():
        session.scalars(select(ReviewEvent)).one().notes_after = "rewritten"
    with pytest.raises(DatabaseError, match="append-only"), services.db.writer() as session, session.begin():
        session.delete(session.scalars(select(ReviewEvent)).one())
    assert events(services, artifact_id)[0].notes_after == "original"


def test_notes_are_never_logged(
    client: TestClient, services: AppServices, caplog: pytest.LogCaptureFixture
) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    add_job(services, artifact_id, minutes=1)
    evidence_id = record_ids(services, artifact_id)["hashes"]
    secret = "SECRET-SOURCE-NAME"

    with caplog.at_level(logging.DEBUG):
        review(client, artifact_id, state="IN_REVIEW", analyst_notes=secret)
        record_review(client, artifact_id, evidence_id, state="REVIEWED", analyst_notes=secret)
        review(
            client,
            artifact_id,
            state="REVIEWED",
            analyst_notes="x",
            expected_updated_at="2020-01-01T00:00:00Z",
        )
        bulk(client, [artifact_id], state="FLAGGED")

    assert caplog.records  # review changes are logged...
    assert secret not in caplog.text  # ...without their notes
