import os
import stat
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import ids
from app.core.config import Settings
from app.core.container import AppServices
from app.main import create_app
from app.models import AnalysisJob, EvidenceRecord
from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageOutput
from app.pipeline.image_pipeline import IMAGE_PIPELINE, IMAGE_STAGES, HashesStage
from app.pipeline.runner import PipelineRunner
from app.schemas.common import EvidenceClassification, MediaType
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok


def start_analysis(client: TestClient, artifact_id: str, options: dict | None = None) -> dict:
    payload: dict = {"artifact_id": artifact_id}
    if options is not None:
        payload["options"] = options
    response = client.post("/api/v1/analysis/image", json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def records_for(services: AppServices, job_id: str) -> list[EvidenceRecord]:
    with services.db.reader() as session:
        stmt = (
            select(EvidenceRecord).where(EvidenceRecord.job_id == job_id).order_by(EvidenceRecord.started_at)
        )
        return list(session.scalars(stmt))


class _TestStage(AnalysisStage):
    media_type = MediaType.IMAGE
    method = "Test stage."
    classification = EvidenceClassification.DERIVED
    source = "artifact:original"
    tool_name = "test-tool"
    limitations = ("Test stage only.",)

    def tool_version(self, ctx: StageContext) -> str:
        return "1.0"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        return StageOutput({"ok": True})


class ExplodingStage(_TestStage):
    name = "exploding"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        raise RuntimeError("boom")


class OptionalStage(_TestStage):
    name = "optional"
    option = "ocr"


class DependentStage(_TestStage):
    name = "dependent"
    depends_on = ("exploding",)


def client_with_stages(settings: Settings, stages: Sequence[AnalysisStage]) -> TestClient:
    app = create_app(
        settings, runner_factory=lambda services: PipelineRunner(services, {IMAGE_PIPELINE: stages})
    )
    return TestClient(app)


def test_analysis_job_runs_and_reports_stage_progress(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]

    created = start_analysis(client, artifact_id)

    assert created["job_id"].startswith("job_")
    assert created["artifact_id"] == artifact_id
    assert created["status"] in ("completed", "completed_with_errors")

    job = client.get(f"/api/v1/analysis/jobs/{created['job_id']}").json()
    assert job["status"] == created["status"]
    assert job["pipeline"] == "image.v1"
    assert [stage["stage"] for stage in job["stages"]] == [stage.name for stage in IMAGE_STAGES]
    assert all(stage["started_at"] and stage["completed_at"] for stage in job["stages"])
    assert job["started_at"] <= job["completed_at"]

    detail = client.get(f"/api/v1/artifacts/{artifact_id}").json()
    assert detail["latest_job"]["job_id"] == created["job_id"]


def test_every_stage_writes_one_complete_evidence_record(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.with_metadata)["artifact_id"]
    job_id = start_analysis(client, artifact_id)["job_id"]

    records = records_for(services, job_id)

    assert [record.stage for record in records] == [stage.name for stage in IMAGE_STAGES]
    for record in records:
        assert record.method
        assert record.tool
        assert record.source
        assert record.limitations and all(isinstance(item, str) and item for item in record.limitations)
        assert isinstance(record.errors, list)
        assert record.review_state == "UNREVIEWED"
        assert record.classification in ("OBSERVED", "DERIVED")
        assert record.started_at <= record.completed_at
        if record.status != "skipped":
            assert record.tool_version, f"{record.stage} has no tool version"


def test_failing_stage_is_recorded_and_the_pipeline_continues(
    settings: Settings, fixtures: FixtureSet
) -> None:
    with client_with_stages(settings, (ExplodingStage(), HashesStage(), DependentStage())) as client:
        services = client.app.state.services
        artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
        job_id = start_analysis(client, artifact_id)["job_id"]

        records = {record.stage: record for record in records_for(services, job_id)}
        job = client.get(f"/api/v1/analysis/jobs/{job_id}").json()

    assert job["status"] == "completed_with_errors"
    assert records["exploding"].status == "failed"
    assert records["exploding"].errors == [{"type": "INTERNAL_ERROR", "message": "RuntimeError: boom"}]
    assert records["exploding"].tool_version == "1.0"
    assert records["hashes"].status == "succeeded"
    assert records["dependent"].status == "skipped"
    assert "exploding" in records["dependent"].payload["skip_reason"]


def test_disabled_option_skips_the_stage_visibly(settings: Settings, fixtures: FixtureSet) -> None:
    with client_with_stages(settings, (HashesStage(), OptionalStage())) as client:
        services = client.app.state.services
        artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
        job_id = start_analysis(client, artifact_id, {"ocr": False})["job_id"]
        records = {record.stage: record for record in records_for(services, job_id)}
        job = client.get(f"/api/v1/analysis/jobs/{job_id}").json()

    assert job["status"] == "completed"
    assert records["optional"].status == "skipped"
    assert records["optional"].payload == {"skip_reason": "Disabled by the analysis option 'ocr'."}
    assert records["optional"].tool_version is None


def test_stage_must_declare_limitations() -> None:
    with pytest.raises(TypeError, match="limitation"):

        class NoLimitations(_TestStage):  # noqa: F841
            name = "no_limitations"
            limitations = ()


def test_hash_mismatch_with_upload_record_fails_the_hashes_stage(
    client: TestClient, services: AppServices, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    stored = settings.data_dir / "artifacts" / artifact_id / "original" / f"{artifact_id}.jpg"
    os.chmod(stored, stat.S_IWUSR | stat.S_IRUSR)
    stored.write_bytes(stored.read_bytes() + b"tampered")

    job_id = start_analysis(client, artifact_id)["job_id"]

    record = next(r for r in records_for(services, job_id) if r.stage == "hashes")
    assert record.status == "failed"
    assert record.errors[0]["type"] == "INTEGRITY_MISMATCH"
    assert record.payload["matches_upload_record"] is False


def _insert_job(services: AppServices, artifact_id: str, status: str) -> str:
    job_id = ids.new_id(ids.JOB)
    with services.db.writer() as session, session.begin():
        session.add(
            AnalysisJob(
                id=job_id,
                artifact_id=artifact_id,
                pipeline=IMAGE_PIPELINE,
                app_version="0.1.0",
                status=status,
                options={},
                created_at=datetime.now(UTC),
            )
        )
    return job_id


def test_only_one_active_job_per_artifact(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    queued_id = _insert_job(services, artifact_id, "queued")

    response = client.post("/api/v1/analysis/image", json={"artifact_id": artifact_id})

    error = assert_error(response, 409, "ANALYSIS_IN_PROGRESS")
    assert error["details"]["job_id"] == queued_id


def test_analysis_can_be_run_again_and_keeps_old_evidence(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    first = start_analysis(client, artifact_id)["job_id"]
    second = start_analysis(client, artifact_id)["job_id"]

    assert first != second
    assert records_for(services, first)
    assert records_for(services, second)


@pytest.mark.parametrize("artifact_id", ["art_" + "0" * 32, "nope"])
def test_analysis_of_unknown_artifact_returns_404(client: TestClient, artifact_id: str) -> None:
    assert_error(
        client.post("/api/v1/analysis/image", json={"artifact_id": artifact_id}), 404, "ARTIFACT_NOT_FOUND"
    )


@pytest.mark.parametrize("job_id", ["job_" + "0" * 32, "job_x", "job_" + "Z" * 32])
def test_unknown_job_returns_404(client: TestClient, job_id: str) -> None:
    assert_error(client.get(f"/api/v1/analysis/jobs/{job_id}"), 404, "JOB_NOT_FOUND")


def test_unknown_analysis_options_are_rejected(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    response = client.post(
        "/api/v1/analysis/image", json={"artifact_id": artifact_id, "options": {"ela": True}}
    )
    assert_error(response, 422, "VALIDATION_ERROR")


def test_thread_mode_runs_jobs_in_the_background(tmp_path: Path, fixtures: FixtureSet) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", job_mode="thread")
    with TestClient(create_app(settings)) as client:
        artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
        job_id = start_analysis(client, artifact_id)["job_id"]

        deadline = time.monotonic() + 60
        status = "queued"
        while status in ("queued", "running") and time.monotonic() < deadline:
            time.sleep(0.1)
            status = client.get(f"/api/v1/analysis/jobs/{job_id}").json()["status"]

    assert status in ("completed", "completed_with_errors")


def test_restart_fails_running_jobs_and_resumes_queued_jobs(settings: Settings, fixtures: FixtureSet) -> None:
    with TestClient(create_app(settings)) as client:
        services = client.app.state.services
        artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
        other_id = upload_ok(client, fixtures.png)["artifact_id"]
        running_id = _insert_job(services, artifact_id, "running")
        queued_id = _insert_job(services, other_id, "queued")

    with TestClient(create_app(settings)) as client:
        running = client.get(f"/api/v1/analysis/jobs/{running_id}").json()
        queued = client.get(f"/api/v1/analysis/jobs/{queued_id}").json()

    assert running["status"] == "failed"
    assert running["error"]["code"] == "INTERRUPTED"
    assert all(stage["status"] == "skipped" for stage in running["stages"])
    assert queued["status"] in ("completed", "completed_with_errors")
