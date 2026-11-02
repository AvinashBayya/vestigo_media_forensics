"""Tool failures must be recorded as evidence, never hidden (04-EVIDENCE-MODEL.md §6)."""

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
