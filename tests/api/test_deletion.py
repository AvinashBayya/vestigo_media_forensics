import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.container import AppServices
from app.models import AnalysisJob, Artifact, DerivedFile, EvidenceRecord, ImageFingerprint
from app.services import artifacts as artifacts_service
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_runner import _insert_job, start_analysis

ROW_MODELS = (Artifact, AnalysisJob, EvidenceRecord, DerivedFile, ImageFingerprint)


def row_counts(services: AppServices, artifact_id: str) -> dict[str, int]:
    counts = {}
    with services.db.reader() as session:
        for model in ROW_MODELS:
            column = model.id if model is Artifact else model.artifact_id
            counts[model.__tablename__] = session.scalar(
                select(func.count()).select_from(model).where(column == artifact_id)
            )
    return counts


def test_delete_removes_files_evidence_and_rows(
    client: TestClient, services: AppServices, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.with_metadata)["artifact_id"]
    start_analysis(client, artifact_id)
    keep_id = upload_ok(client, fixtures.png)["artifact_id"]
    start_analysis(client, keep_id)
    artifact_dir = settings.data_dir / "artifacts" / artifact_id
    assert all(count > 0 for count in row_counts(services, artifact_id).values())

    response = client.delete(f"/api/v1/artifacts/{artifact_id}")

    assert response.status_code == 200
    assert response.json() == {
        "artifact_id": artifact_id,
        "original_files": 1,
        "derived_files": 3,  # ExifTool metadata JSON, ExifTool C2PA JSON, Tesseract TSV
        "jobs": 1,
        "evidence_records": 6,
    }
    assert not artifact_dir.exists()
    assert list((settings.data_dir / "trash").iterdir()) == []
    assert row_counts(services, artifact_id) == {model.__tablename__: 0 for model in ROW_MODELS}
    assert_error(client.get(f"/api/v1/artifacts/{artifact_id}"), 404, "ARTIFACT_NOT_FOUND")
    assert_error(client.get(f"/api/v1/artifacts/{artifact_id}/content"), 404, "ARTIFACT_NOT_FOUND")
    assert_error(client.get(f"/api/v1/artifacts/{artifact_id}/evidence"), 404, "ARTIFACT_NOT_FOUND")

    # Other artifacts are untouched.
    assert client.get(f"/api/v1/artifacts/{keep_id}/evidence").status_code == 200
    assert (settings.data_dir / "artifacts" / keep_id).is_dir()


def test_deleted_artifact_disappears_from_duplicate_results(client: TestClient, fixtures: FixtureSet) -> None:
    deleted_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    start_analysis(client, deleted_id)
    keep_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    start_analysis(client, keep_id)

    client.delete(f"/api/v1/artifacts/{deleted_id}")

    # The earlier report still records the match, but no longer names the deleted file.
    old_match = client.get(f"/api/v1/artifacts/{keep_id}/evidence").json()["duplicates"]["matches"][0]
    assert old_match["artifact_id"] == deleted_id
    assert old_match["available"] is False
    assert old_match["filename"] is None

    start_analysis(client, keep_id)
    assert client.get(f"/api/v1/artifacts/{keep_id}/evidence").json()["duplicates"]["matches"] == []


def test_delete_is_refused_while_analysis_is_active(
    client: TestClient, services: AppServices, settings: Settings, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    _insert_job(services, artifact_id, "running")

    assert_error(client.delete(f"/api/v1/artifacts/{artifact_id}"), 409, "ANALYSIS_IN_PROGRESS")
    assert (settings.data_dir / "artifacts" / artifact_id).is_dir()


@pytest.mark.parametrize("artifact_id", ["art_" + "0" * 32, "bogus"])
def test_delete_unknown_artifact_returns_404(client: TestClient, artifact_id: str) -> None:
    assert_error(client.delete(f"/api/v1/artifacts/{artifact_id}"), 404, "ARTIFACT_NOT_FOUND")


def test_files_are_restored_if_the_database_deletion_fails(
    client: TestClient, services: AppServices, settings: Settings, fixtures: FixtureSet, monkeypatch
) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]

    def failing_delete(session, artifact_id: str) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(artifacts_service, "_delete_rows", failing_delete)
    with pytest.raises(RuntimeError):
        client.delete(f"/api/v1/artifacts/{artifact_id}")

    assert (settings.data_dir / "artifacts" / artifact_id / "original").is_dir()
    assert row_counts(services, artifact_id)["artifacts"] == 1
    assert client.get(f"/api/v1/artifacts/{artifact_id}/content").status_code == 200
