import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.container import AppServices
from app.models import EvidenceRecord
from app.schemas.common import EvidenceClassification, JobStatus, ReviewState, StageStatus
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_runner import _insert_job, start_analysis

SECTIONS = ("hashes", "metadata", "c2pa", "perceptual_hash", "ocr", "duplicates")
PROVENANCE_FIELDS = {
    "evidence_id",
    "stage",
    "status",
    "classification",
    "method",
    "source",
    "tool",
    "tool_version",
    "started_at",
    "completed_at",
    "limitations",
    "errors",
    "review_state",
    "skip_reason",
    "derived_files",
    "analyst_notes",
    "review_updated_at",
}
VERDICT_WORDS = re.compile(
    r"authentic|fake|\breal\b|verdict|genuine|manipulat|deepfake|forg|tamper|truth|suspicious",
    re.IGNORECASE,
)


def analysed_report(client: TestClient, path, options: dict | None = None) -> dict:
    artifact_id = upload_ok(client, path)["artifact_id"]
    start_analysis(client, artifact_id, options)
    response = client.get(f"/api/v1/artifacts/{artifact_id}/evidence")
    assert response.status_code == 200, response.text
    return response.json()


def test_report_keeps_the_03_shape_and_adds_provenance(client: TestClient, fixtures: FixtureSet) -> None:
    report = analysed_report(client, fixtures.with_metadata)

    assert report["schema_version"] == "1.1"
    assert report["artifact_id"].startswith("art_")
    assert report["job_id"].startswith("job_")
    assert report["created_at"].endswith("Z")
    assert "does not determine whether the media is authentic" in report["notice"]
    assert report["hashes"]["sha256"] and report["hashes"]["md5"]
    assert set(report["metadata"]) >= {"exif", "xmp", "iptc"}
    assert report["metadata"]["exif"]["IFD0"]["Make"] == "VestigoTestCam"
    assert report["c2pa"]["present"] is False
    assert report["c2pa"]["validation_performed"] is False
    assert report["perceptual_hash"]["algorithm"] == "pHash"
    assert report["ocr"]["engine"] == "tesseract"
    assert report["duplicates"]["matches"] == []
    assert report["review"] == {
        "state": "UNREVIEWED",
        "analyst_notes": "",
        "updated_at": report["review"]["updated_at"],
    }


def test_every_section_carries_complete_provenance(client: TestClient, fixtures: FixtureSet) -> None:
    report = analysed_report(client, fixtures.with_metadata)

    for name in SECTIONS:
        provenance = report[name]["provenance"]
        assert set(provenance) == PROVENANCE_FIELDS, name
        assert provenance["stage"] == name
        assert provenance["method"] and provenance["tool"] and provenance["source"]
        assert provenance["tool_version"], name
        assert provenance["started_at"] <= provenance["completed_at"]
        assert provenance["limitations"]
        assert provenance["review_state"] == "UNREVIEWED"
        assert provenance["classification"] in ("OBSERVED", "DERIVED")

    assert [f["kind"] for f in report["metadata"]["provenance"]["derived_files"]] == ["exiftool_json"]
    assert [f["kind"] for f in report["ocr"]["provenance"]["derived_files"]] == [
        "ocr_input_grayscale",
        "tesseract_tsv_grayscale",
        "ocr_input_threshold",
        "tesseract_tsv_threshold",
    ]


def test_skipped_and_failed_stages_are_visible_in_the_report(
    client: TestClient, settings, fixtures: FixtureSet
) -> None:
    report = analysed_report(client, fixtures.corrupt_exif, {"ocr": False})

    assert report["ocr"]["provenance"]["status"] == "skipped"
    assert report["ocr"]["provenance"]["skip_reason"] == "Disabled by the analysis option 'ocr'."
    assert report["hashes"]["provenance"]["skip_reason"] is None
    assert report["ocr"]["text"] == ""
    assert report["metadata"]["provenance"]["status"] == "partial"
    assert report["metadata"]["provenance"]["errors"]
    assert report["job"]["status"] == "completed_with_errors"


def test_ocr_section_reports_preprocessing_candidates_and_selection(
    client: TestClient, fixtures: FixtureSet
) -> None:
    ocr = analysed_report(client, fixtures.ocr_noisy)["ocr"]

    assert ocr["text"]
    assert ocr["selected"]["variant"] == "threshold"
    assert ocr["selected"]["reason"]
    assert [c["variant"] for c in ocr["candidates"]] == ["grayscale", "threshold"]
    assert {c["status"] for c in ocr["candidates"]} == {"succeeded"}
    assert ocr["text"] == ocr["candidates"][1]["text"]
    steps = {step["step"]: step for step in ocr["preprocessing"]}
    assert steps["grayscale"]["applied"] is True
    assert steps["upscale"]["parameters"]["factor"] == 2
    assert steps["adaptive_threshold"]["parameters"]["offset"] == 20
    assert "cleaned_text" in ocr and "cleaning" in ocr
    provenance = ocr["provenance"]
    assert "Pillow" in provenance["tool_version"]
    assert "adaptive threshold" in provenance["method"]
    assert any("not measured accuracy" in item for item in provenance["limitations"])


def test_ocr_cleaned_text_is_separate_from_raw_text(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.ocr_text)["artifact_id"]
    start_analysis(client, artifact_id)
    raw = "VESTIGO SAMPLE  \n|\n2026"
    _replace_ocr_payload(services, artifact_id, {"text": raw, "cleaned_text": "VESTIGO SAMPLE\n2026"})

    ocr = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["ocr"]
    assert ocr["text"] == raw
    assert ocr["cleaned_text"] == "VESTIGO SAMPLE\n2026"


def test_ocr_records_from_before_two_pass_ocr_still_render(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.ocr_text)["artifact_id"]
    start_analysis(client, artifact_id)
    legacy = {
        "engine": "tesseract",
        "languages": ["eng"],
        "text": "VESTIGO EVIDENCE SAMPLE 2026",
        "confidence": 0.95,
        "word_count": 4,
        "preprocessing": ["Converted to an 8-bit RGB PNG."],
    }
    _replace_ocr_payload(services, artifact_id, legacy, replace=True)

    response = client.get(f"/api/v1/artifacts/{artifact_id}/evidence")
    assert response.status_code == 200, response.text
    ocr = response.json()["ocr"]
    assert ocr["text"] == legacy["text"]
    assert ocr["cleaned_text"] is None
    assert ocr["cleaning"] == []
    assert ocr["candidates"] == []
    assert ocr["selected"] is None
    assert ocr["preprocessing"] == [
        {"step": "note", "applied": True, "description": "Converted to an 8-bit RGB PNG.", "parameters": {}}
    ]


def _replace_ocr_payload(
    services: AppServices, artifact_id: str, payload: dict[str, Any], replace: bool = False
) -> None:
    with services.db.writer() as session, session.begin():
        record = session.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.artifact_id == artifact_id, EvidenceRecord.stage == "ocr"
            )
        ).one()
        record.payload = payload if replace else {**record.payload, **payload}


def test_duplicate_matches_show_current_filenames(client: TestClient, fixtures: FixtureSet) -> None:
    first = upload_ok(client, fixtures.jpeg, filename="first.jpg")["artifact_id"]
    report = analysed_report(client, fixtures.jpeg)

    assert report["duplicates"]["matches"] == [
        {
            "artifact_id": first,
            "filename": "first.jpg",
            "available": True,
            "similarity": 1.0,
            "distance": 0,
            "match_type": "exact_file",
        }
    ]


def test_evidence_can_be_downloaded(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    job_id = start_analysis(client, artifact_id)["job_id"]

    response = client.get(f"/api/v1/artifacts/{artifact_id}/evidence", params={"download": "true"})

    assert response.status_code == 200
    expected = f'attachment; filename="vestigo-evidence-{artifact_id}-{job_id}.json"'
    assert response.headers["content-disposition"] == expected
    assert response.json()["job_id"] == job_id


def test_report_for_a_specific_job(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    first = start_analysis(client, artifact_id)["job_id"]
    second = start_analysis(client, artifact_id)["job_id"]

    latest = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    earlier = client.get(f"/api/v1/artifacts/{artifact_id}/evidence", params={"job_id": first}).json()

    assert latest["job_id"] == second
    assert earlier["job_id"] == first


def test_evidence_before_any_analysis_returns_404(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    assert_error(client.get(f"/api/v1/artifacts/{artifact_id}/evidence"), 404, "EVIDENCE_NOT_FOUND")


def test_evidence_errors(client: TestClient, services: AppServices, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    other_id = upload_ok(client, fixtures.png)["artifact_id"]
    other_job = start_analysis(client, other_id)["job_id"]
    running_job = _insert_job(services, artifact_id, "running")
    url = f"/api/v1/artifacts/{artifact_id}/evidence"

    assert_error(client.get(f"/api/v1/artifacts/art_{'0' * 32}/evidence"), 404, "ARTIFACT_NOT_FOUND")
    assert_error(client.get(url, params={"job_id": other_job}), 404, "JOB_NOT_FOUND")
    assert_error(client.get(url, params={"job_id": "job_bad"}), 404, "JOB_NOT_FOUND")
    assert_error(client.get(url, params={"job_id": running_job}), 409, "ANALYSIS_IN_PROGRESS")


def _keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            # Metadata and C2PA sections hold keys written by the file's creator, not by Vestigo.
            if key not in ("exif", "xmp", "iptc", "other", "composite", "details"):
                yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


@pytest.mark.parametrize("fixture_name", ["jpeg", "c2pa", "invalid_c2pa"])
def test_reports_contain_no_verdict_wording(
    client: TestClient, fixtures: FixtureSet, fixture_name: str
) -> None:
    report = analysed_report(client, getattr(fixtures, fixture_name))

    for key in _keys(report):
        assert not VERDICT_WORDS.search(key), key
    assert "confidence" not in report  # no overall score; OCR confidence lives inside the OCR section
    assert "verdict" not in report


def test_enums_contain_no_verdict_values() -> None:
    for enum in (ReviewState, EvidenceClassification, JobStatus, StageStatus):
        for member in enum:
            assert not VERDICT_WORDS.search(member.value), member
