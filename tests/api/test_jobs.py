"""GET /artifacts/{id}/jobs: analysis history (M2 step 7)."""

from fastapi.testclient import TestClient

from app.core.container import AppServices
from app.models import AnalysisJob
from tests.api.test_library import add_artifact, add_job
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_runner import start_analysis


def test_job_history_lists_every_job_newest_first(client: TestClient, services: AppServices) -> None:
    artifact_id = add_artifact(services, "a.jpg")
    first = add_job(services, artifact_id, minutes=1, stages={"metadata": "partial", "ocr": "failed"})
    second = add_job(services, artifact_id, minutes=2, status="failed", stages={"hashes": "succeeded"})
    with services.db.writer() as session, session.begin():
        job = session.get(AnalysisJob, second)
        job.error_code = "INTERRUPTED"
        job.error_message = "The service restarted while this analysis was running. Run it again."

    history = client.get(f"/api/v1/artifacts/{artifact_id}/jobs").json()

    assert history["artifact_id"] == artifact_id
    assert [job["job_id"] for job in history["jobs"]] == [second, first]
    latest, earlier = history["jobs"]
    assert latest["status"] == "failed"
    assert latest["error"] == {
        "code": "INTERRUPTED",
        "message": "The service restarted while this analysis was running. Run it again.",
        "details": {},
    }
    assert latest["problem_count"] == 1  # the failed job itself
    assert earlier["error"] is None
    assert earlier["problem_count"] == 2
    assert earlier["pipeline"] == "image.v1"
    assert earlier["app_version"] == "0.1.0"
    assert earlier["options"] == {"metadata": True, "c2pa": True, "ocr": True, "duplicate_search": True}


def test_job_history_of_real_analyses(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    assert client.get(f"/api/v1/artifacts/{artifact_id}/jobs").json()["jobs"] == []

    start_analysis(client, artifact_id, {"ocr": False})
    [job] = client.get(f"/api/v1/artifacts/{artifact_id}/jobs").json()["jobs"]
    assert job["status"] == "completed"
    assert job["options"]["ocr"] is False
    assert job["problem_count"] == 0
    assert job["completed_at"]


def test_job_history_not_found(client: TestClient) -> None:
    assert_error(client.get(f"/api/v1/artifacts/{'art_' + '0' * 32}/jobs"), 404, "ARTIFACT_NOT_FOUND")
    assert_error(client.get("/api/v1/artifacts/not-an-id/jobs"), 404, "ARTIFACT_NOT_FOUND")
