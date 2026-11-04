"""ZIP evidence package (M2-6)."""

import hashlib
import io
import json
import logging
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import AppServices
from app.schemas.evidence import REPORT_NOTICE
from tests.api.test_evidence import VERDICT_WORDS, _keys
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_runner import _insert_job, start_analysis

DERIVED = {
    "derived/c2pa.exiftool.json",
    "derived/metadata.exiftool.json",
    "derived/ocr.grayscale.png",
    "derived/ocr.grayscale.tsv",
    "derived/ocr.threshold.png",
    "derived/ocr.threshold.tsv",
}


def analysed(client: TestClient, path: Path) -> tuple[str, str]:
    artifact_id = upload_ok(client, path)["artifact_id"]
    return artifact_id, start_analysis(client, artifact_id)["job_id"]


def export(client: TestClient, artifact_id: str, **params: object) -> tuple[zipfile.ZipFile, dict, bytes]:
    response = client.get(f"/api/v1/artifacts/{artifact_id}/export", params=params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-vestigo-export-sha256"] == hashlib.sha256(response.content).hexdigest()
    package = zipfile.ZipFile(io.BytesIO(response.content))
    return package, json.loads(package.read("manifest.json")), response.content


def test_package_contents_and_verification(
    client: TestClient, services: AppServices, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analysed(client, fixtures.ocr_text)
    client.patch(
        f"/api/v1/artifacts/{artifact_id}/review", json={"state": "IN_REVIEW", "analyst_notes": "Checking."}
    )

    response = client.get(f"/api/v1/artifacts/{artifact_id}/export")
    package, manifest, _ = export(client, artifact_id)

    assert response.headers["content-disposition"] == (
        f'attachment; filename="vestigo-evidence-{artifact_id}-{job_id}.zip"'
    )
    names = set(package.namelist())
    assert names == {"report.json", "review.json", "README.txt", "manifest.json", "SHA256SUMS", *DERIVED}
    assert not any(name.startswith("original/") for name in names)  # not included by default

    assert manifest["format"] == "vestigo-evidence-package"
    assert (manifest["artifact_id"], manifest["job_id"]) == (artifact_id, job_id)
    assert manifest["original_included"] is False
    assert manifest["report_schema_version"] == "1.2"
    assert manifest["notice"] == REPORT_NOTICE
    assert manifest["problems"] == []
    # Every listed file is in the ZIP with that SHA-256 and size, and SHA256SUMS says the same.
    listed = {entry["path"]: entry for entry in manifest["files"]}
    assert set(listed) == names - {"manifest.json", "SHA256SUMS"}
    for path, entry in listed.items():
        data = package.read(path)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest(), path
        assert entry["size_bytes"] == len(data)
    sums = dict(reversed(line.split("  ", 1)) for line in package.read("SHA256SUMS").decode().splitlines())
    assert sums == {path: entry["sha256"] for path, entry in listed.items()}
    for path in DERIVED:
        assert listed[path]["matches_record"] is True
        assert listed[path]["recorded_sha256"] == listed[path]["sha256"]

    report = json.loads(package.read("report.json"))
    live = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    report.pop("created_at"), live.pop("created_at")
    assert report == live

    review = json.loads(package.read("review.json"))
    assert review["artifact_review"]["analyst_notes"] == "Checking."
    assert len(review["record_reviews"]) == 6
    assert {r["classification"] for r in review["record_reviews"]} <= {"OBSERVED", "DERIVED"}
    assert review["review_history"][0]["notes_after"] == "Checking."

    readme = package.read("README.txt").decode()
    assert REPORT_NOTICE in readme
    assert "sha256sum -c SHA256SUMS" in readme
    assert "X-Vestigo-Export-SHA256" in readme

    assert list((settings.data_dir / "tmp").iterdir()) == []  # the temporary package was removed


def test_original_is_included_only_on_request(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, _ = analysed(client, fixtures.jpeg)

    package, manifest, _ = export(client, artifact_id, include_original="true")

    originals = [name for name in package.namelist() if name.startswith("original/")]
    assert originals == [f"original/{artifact_id}.jpg"]
    assert package.read(originals[0]) == fixtures.jpeg.read_bytes()
    entry = next(e for e in manifest["files"] if e["path"] == originals[0])
    assert entry["original_filename"] == fixtures.jpeg.name
    assert entry["matches_record"] is True
    assert manifest["original_included"] is True


def test_export_of_an_earlier_job(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id, first_job = analysed(client, fixtures.jpeg)
    second_job = start_analysis(client, artifact_id, {"ocr": False})["job_id"]

    _, manifest, _ = export(client, artifact_id)
    assert manifest["job_id"] == second_job
    package, manifest, _ = export(client, artifact_id, job_id=first_job)
    assert manifest["job_id"] == first_job
    assert json.loads(package.read("report.json"))["job_id"] == first_job
    assert "derived/ocr.grayscale.tsv" in package.namelist()


def test_missing_or_changed_derived_files_are_reported(
    client: TestClient, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id, job_id = analysed(client, fixtures.jpeg)
    derived = settings.data_dir / "artifacts" / artifact_id / "derived" / job_id
    (derived / "ocr.threshold.tsv").unlink()
    changed = derived / "metadata.exiftool.json"
    changed.chmod(0o644)
    changed.write_bytes(changed.read_bytes() + b" ")

    package, manifest, _ = export(client, artifact_id)

    assert "derived/ocr.threshold.tsv" not in package.namelist()
    problems = {(p["path"], p["problem"]) for p in manifest["problems"]}
    assert problems == {
        ("derived/ocr.threshold.tsv", "missing"),
        ("derived/metadata.exiftool.json", "sha256_mismatch"),
    }
    entry = next(e for e in manifest["files"] if e["path"] == "derived/metadata.exiftool.json")
    assert entry["matches_record"] is False


def test_export_errors(client: TestClient, services: AppServices, fixtures: FixtureSet) -> None:
    assert_error(client.get(f"/api/v1/artifacts/{'art_' + '0' * 32}/export"), 404, "ARTIFACT_NOT_FOUND")
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    assert_error(client.get(f"/api/v1/artifacts/{artifact_id}/export"), 404, "EVIDENCE_NOT_FOUND")
    assert_error(
        client.get(f"/api/v1/artifacts/{artifact_id}/export", params={"job_id": "job_" + "0" * 32}),
        404,
        "JOB_NOT_FOUND",
    )
    running = _insert_job(services, artifact_id, "running")
    assert_error(
        client.get(f"/api/v1/artifacts/{artifact_id}/export", params={"job_id": running}),
        409,
        "ANALYSIS_IN_PROGRESS",
    )


def test_write_failure_returns_export_failed_and_leaves_nothing(
    client: TestClient, settings: Settings, fixtures: FixtureSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_id, _ = analysed(client, fixtures.jpeg)

    def disk_full(*args: object, **kwargs: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(zipfile.ZipFile, "write", disk_full)
    assert_error(client.get(f"/api/v1/artifacts/{artifact_id}/export"), 500, "EXPORT_FAILED")
    assert list((settings.data_dir / "tmp").iterdir()) == []


def test_package_has_no_verdict_wording_and_notes_stay_out_of_logs(
    client: TestClient, fixtures: FixtureSet, caplog: pytest.LogCaptureFixture
) -> None:
    artifact_id, _ = analysed(client, fixtures.jpeg)
    client.patch(
        f"/api/v1/artifacts/{artifact_id}/review", json={"state": "FLAGGED", "analyst_notes": "SECRET-NOTE"}
    )

    with caplog.at_level(logging.DEBUG):
        package, manifest, _ = export(client, artifact_id)

    for document in (manifest, json.loads(package.read("review.json"))):
        assert not [key for key in _keys(document) if VERDICT_WORDS.search(key)]
    assert "SECRET-NOTE" in package.read("review.json").decode()
    assert "SECRET-NOTE" not in caplog.text
    assert "export.created" in caplog.text
