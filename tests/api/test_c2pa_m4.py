"""Milestone 4: C2PA validation end to end across image, video, and audio artifacts."""

import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.core.container import AppServices
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import upload_ok
from tests.pipeline.test_runner import records_for, start_analysis


def analysed_c2pa(client: TestClient, path, kind: str) -> tuple[str, dict]:
    artifact_id = upload_ok(client, path)["artifact_id"]
    response = client.post(f"/api/v1/analysis/{kind}", json={"artifact_id": artifact_id})
    assert response.status_code == 202, response.text
    report = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()
    return artifact_id, report["c2pa"]


def test_valid_c2pa_across_media_types(client: TestClient, fixtures: FixtureSet) -> None:
    cases = [
        (fixtures.c2pa_signed_jpeg, "image"),
        (fixtures.c2pa_signed_mp4, "video"),
        (fixtures.c2pa_signed_wav, "audio"),
    ]
    for path, kind in cases:
        _, section = analysed_c2pa(client, path, kind)
        assert section["present"] is True, kind
        assert section["validation_performed"] is True
        assert section["status"] == "valid"
        assert section["validation_state"] == "Valid"
        assert section["manifest_count"] == 1
        [manifest] = section["manifests"]
        assert manifest["signature_issuer"] == "Vestigo Test"
        assert manifest["claim_generator"] == "Vestigo Test Fixture 1.0"
        assert manifest["signature_time"] is None or isinstance(manifest["signature_time"], str)
        assert "c2pa.actions" in " ".join(manifest["assertion_labels"])
        assert section["validator"].startswith("c2pa-python")
        # Untrusted-signer is reported, never hidden: no trust list is configured.
        failure_codes = [code["code"] for code in section["validation_codes"]["failure"]]
        assert failure_codes == ["signingCredential.untrusted"], kind
        provenance = section["provenance"]
        assert any("does NOT prove" in item for item in provenance["limitations"])
        assert any("Absence of C2PA data is normal" in item for item in provenance["limitations"])
        kinds = [f["kind"] for f in provenance["derived_files"]]
        assert "c2pa_manifest_store" in kinds, kind


def test_invalid_c2pa_is_reported_with_the_failure(client: TestClient, fixtures: FixtureSet) -> None:
    _, section = analysed_c2pa(client, fixtures.c2pa_tampered, "image")
    assert section["present"] is True
    assert section["status"] == "invalid"
    assert section["validation_state"] == "Invalid"
    failures = [code["code"] for code in section["validation_codes"]["failure"]]
    assert "assertion.dataHash.mismatch" in failures
    # The stage itself succeeded: an invalid manifest is a finding, not a tool failure.
    assert section["provenance"]["status"] == "succeeded"


def test_multiple_manifests_are_reported(client: TestClient, fixtures: FixtureSet) -> None:
    _, section = analysed_c2pa(client, fixtures.c2pa_multi_manifest, "image")
    assert section["status"] == "valid"
    assert section["manifest_count"] == 2
    assert len(section["manifests"]) == 2
    assert section["active_manifest"] in section["manifest_labels"]
    generators = {m["claim_generator"] for m in section["manifests"]}
    assert "Vestigo Test Fixture Second Pass 1.0" in generators


def test_absent_c2pa_across_media_types(client: TestClient, fixtures: FixtureSet) -> None:
    for path, kind in (
        (fixtures.png, "image"),
        (fixtures.video_static, "video"),
        (fixtures.audio_mp3, "audio"),
    ):
        _, section = analysed_c2pa(client, path, kind)
        assert section["present"] is False, kind
        assert section["status"] == "absent"
        assert section["manifest_count"] == 0
        assert section["manifests"] == []
        assert section["provenance"]["status"] == "succeeded"


def test_unsupported_container_is_unverifiable(client: TestClient, fixtures: FixtureSet) -> None:
    _, section = analysed_c2pa(client, fixtures.video_mkv, "video")
    assert section["status"] == "unverifiable"
    assert "unsupported format" in section["validator_error"]
    assert section["present"] is False


def test_raw_manifest_store_is_exported_and_deleted(
    client: TestClient, services: AppServices, settings, fixtures: FixtureSet
) -> None:
    artifact_id = upload_ok(client, fixtures.c2pa_signed_jpeg)["artifact_id"]
    job_id = start_analysis(client, artifact_id)["job_id"]

    stored = settings.data_dir / "artifacts" / artifact_id / "derived" / job_id / "c2pa.manifest_store.json"
    assert stored.is_file()
    assert json.loads(stored.read_bytes())["validation_state"] == "Valid"

    package = zipfile.ZipFile(io.BytesIO(client.get(f"/api/v1/artifacts/{artifact_id}/export").content))
    assert "derived/c2pa.manifest_store.json" in package.namelist()

    assert client.delete(f"/api/v1/artifacts/{artifact_id}").status_code == 200
    assert not stored.exists()
    assert records_for(services, job_id) == []


def test_c2pa_can_be_disabled_for_video_and_audio(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    for path, kind in ((fixtures.video_static, "video"), (fixtures.audio_wav, "audio")):
        artifact_id = upload_ok(client, path)["artifact_id"]
        response = client.post(
            f"/api/v1/analysis/{kind}", json={"artifact_id": artifact_id, "options": {"c2pa": False}}
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        record = next(r for r in records_for(services, job_id) if r.stage == "c2pa")
        assert record.status == "skipped", kind
        assert record.payload["skip_reason"] == "Disabled by the analysis option 'c2pa'."
