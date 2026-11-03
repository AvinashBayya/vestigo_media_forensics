"""Tool failures must be recorded as evidence, never hidden (04-EVIDENCE-MODEL.md §6)."""

import hashlib
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import upload_ok
from tests.pipeline.test_runner import records_for, start_analysis
from tests.unit.test_metadata import fake_tool, registry_with

FAKE_EXIFTOOL_VERSION = 'if [ "$1" = "-ver" ]; then echo 13.25; exit 0; fi'


@pytest.mark.parametrize(
    ("script", "error_type"),
    [
        (f"{FAKE_EXIFTOOL_VERSION}\nsleep 5", "TOOL_TIMEOUT"),
        (f"{FAKE_EXIFTOOL_VERSION}\necho 'this is not json'", "TOOL_OUTPUT_INVALID"),
        (f"{FAKE_EXIFTOOL_VERSION}\necho 'Error: boom' >&2; exit 1", "TOOL_ERROR"),
    ],
)
def test_metadata_tool_failures_are_recorded(
    tmp_path: Path, fixtures: FixtureSet, script: str, error_type: str
) -> None:
    exiftool = fake_tool(tmp_path, "exiftool", script)
    settings = Settings(
        _env_file=None, data_dir=tmp_path / "data", job_mode="inline", tool_timeout_seconds=0.5
    )
    app = create_app(settings, tools=registry_with({"exiftool": exiftool}))

    with TestClient(app) as client:
        artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
        created = start_analysis(client, artifact_id)
        record = next(r for r in records_for(app.state.services, created["job_id"]) if r.stage == "metadata")

    assert created["status"] == "completed_with_errors"
    assert record.status == "failed"
    assert record.errors[0]["type"] == error_type
    assert record.tool_version == "13.25"
    assert record.limitations


def test_missing_tool_is_recorded_as_unavailable(tmp_path: Path, fixtures: FixtureSet) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", job_mode="inline")
    app = create_app(settings, tools=registry_with({"exiftool": None}))

    with TestClient(app) as client:
        artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
        job_id = start_analysis(client, artifact_id)["job_id"]
        record = next(r for r in records_for(app.state.services, job_id) if r.stage == "metadata")

    assert record.status == "failed"
    assert record.errors[0]["type"] == "TOOL_UNAVAILABLE"
    assert record.tool_version is None


def test_metadata_stage_saves_raw_tool_output(
    client: TestClient, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.with_metadata)["artifact_id"]
    job_id = start_analysis(client, artifact_id)["job_id"]

    raw = settings.data_dir / "artifacts" / artifact_id / "derived" / job_id / "metadata.exiftool.json"
    assert raw.is_file()
    assert b"VestigoTestCam" in raw.read_bytes()


def test_corrupt_metadata_makes_the_stage_partial(client: TestClient, fixtures: FixtureSet, services) -> None:
    artifact_id = upload_ok(client, fixtures.corrupt_exif)["artifact_id"]
    job_id = start_analysis(client, artifact_id)["job_id"]

    record = next(r for r in records_for(services, job_id) if r.stage == "metadata")
    assert record.status == "partial"
    assert record.errors[0]["type"] == "EXIFTOOL_WARNING"


FAKE_TESSERACT = """
if [ "$1" = "--version" ]; then echo "tesseract 5.5.0"; exit 0; fi
if [ "$1" = "--list-langs" ]; then printf 'List of available languages (1):\\neng\\n'; exit 0; fi
echo "Error: could not initialise" >&2
exit 1
"""


def test_ocr_failure_is_recorded(tmp_path: Path, fixtures: FixtureSet) -> None:
    tesseract = fake_tool(tmp_path, "tesseract", FAKE_TESSERACT)
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", job_mode="inline")
    app = create_app(settings, tools=registry_with({"tesseract": tesseract}))

    with TestClient(app) as client:
        artifact_id = upload_ok(client, fixtures.ocr_text)["artifact_id"]
        job_id = start_analysis(client, artifact_id)["job_id"]
        record = next(r for r in records_for(app.state.services, job_id) if r.stage == "ocr")

    assert record.status == "failed"
    assert record.errors[0]["type"] == "TOOL_ERROR"
    assert "could not initialise" in record.errors[0]["message"]


def test_ocr_stage_records_text_and_raw_output(
    client: TestClient, settings: Settings, fixtures: FixtureSet, services
) -> None:
    artifact_id = upload_ok(client, fixtures.ocr_text)["artifact_id"]
    job_id = start_analysis(client, artifact_id)["job_id"]

    record = next(r for r in records_for(services, job_id) if r.stage == "ocr")
    assert record.status == "succeeded"
    assert record.errors == []
    assert "VESTIGO" in record.payload["text"].upper()
    assert record.payload["languages"] == ["eng"]
    assert record.payload["selected"]["variant"] in ("grayscale", "threshold")
    assert [c["variant"] for c in record.payload["candidates"]] == ["grayscale", "threshold"]
    assert "Pillow" in record.tool_version
    derived = settings.data_dir / "artifacts" / artifact_id / "derived" / job_id
    for name in ("ocr.grayscale.png", "ocr.grayscale.tsv", "ocr.threshold.png", "ocr.threshold.tsv"):
        assert (derived / name).is_file(), name


def test_ocr_preprocessing_leaves_the_original_unchanged(
    client: TestClient, settings: Settings, fixtures: FixtureSet, services
) -> None:
    uploaded = upload_ok(client, fixtures.ocr_low_res)
    artifact_id = uploaded["artifact_id"]
    start_analysis(client, artifact_id)

    originals = list((settings.data_dir / "artifacts" / artifact_id / "original").iterdir())
    assert len(originals) == 1
    assert originals[0].read_bytes() == fixtures.ocr_low_res.read_bytes()
    assert hashlib.sha256(originals[0].read_bytes()).hexdigest() == uploaded["sha256"]


def test_ocr_threshold_pass_failure_makes_the_stage_partial(tmp_path: Path, fixtures: FixtureSet) -> None:
    real = shutil.which("tesseract")
    assert real
    # Fails only when given the threshold image; everything else goes to the real Tesseract.
    tesseract = fake_tool(
        tmp_path,
        "tesseract",
        'case "$(basename "$1")" in *threshold*) echo "Error: threshold boom" >&2; exit 1;; esac\n'
        f'exec {real} "$@"',
    )
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", job_mode="inline")
    app = create_app(settings, tools=registry_with({"tesseract": tesseract}))

    with TestClient(app) as client:
        artifact_id = upload_ok(client, fixtures.ocr_text)["artifact_id"]
        created = start_analysis(client, artifact_id)
        record = next(r for r in records_for(app.state.services, created["job_id"]) if r.stage == "ocr")

    assert created["status"] == "completed_with_errors"
    assert record.status == "partial"
    assert [e["type"] for e in record.errors] == ["OCR_VARIANT_FAILED"]
    assert "threshold boom" in record.errors[0]["message"]
    assert "VESTIGO" in record.payload["text"].upper()
    assert record.payload["selected"]["variant"] == "grayscale"
    assert record.payload["candidates"][1]["status"] == "failed"
    derived = settings.data_dir / "artifacts" / artifact_id / "derived" / created["job_id"]
    assert (derived / "ocr.grayscale.tsv").is_file()
    assert (derived / "ocr.threshold.png").is_file()
    assert not (derived / "ocr.threshold.tsv").exists()
