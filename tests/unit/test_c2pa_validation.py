"""Local C2PA manifest reading and validation (M4, D20)."""

from app.services.c2pa import c2pa_validator_version, read_manifest_store
from tests.fixtures.make_fixtures import FixtureSet


def test_validator_version_names_the_exact_tool() -> None:
    version = c2pa_validator_version()
    assert version.startswith("c2pa-python 0.")
    assert "c2pa-rs" in version


def test_valid_signed_media(fixtures: FixtureSet) -> None:
    for name in ("c2pa_signed_jpeg", "c2pa_signed_mp4", "c2pa_signed_wav"):
        result = read_manifest_store(getattr(fixtures, name))
        assert result.status == "valid", name
        assert result.validation_state == "Valid"
        assert result.manifest_count == 1
        assert result.active_manifest
        [manifest] = result.manifests
        assert manifest.signature_issuer == "Vestigo Test"
        assert manifest.signature_common_name == "Vestigo Test Signer"
        assert manifest.signature_algorithm
        assert "c2pa.actions" in " ".join(manifest.assertion_labels)
        assert result.raw_report and b"manifests" in result.raw_report
        # No trust list is configured, so the SDK reports the signer as untrusted even though the
        # signature and hashes verify (overall state Valid). That nuance is surfaced, never hidden.
        failure_codes = [code["code"] for code in result.validation_codes["failure"]]
        assert failure_codes == ["signingCredential.untrusted"]
        assert result.error is None


def test_real_world_sample_parses_and_validates(fixtures: FixtureSet) -> None:
    result = read_manifest_store(fixtures.c2pa)
    assert result.status == "valid"
    [manifest] = result.manifests
    assert manifest.claim_generator == "make_test_images/0.16.1 c2pa-rs/0.16.1"
    assert manifest.signature_issuer == "C2PA Test Signing Cert"
    assert manifest.signature_time  # RFC3161 timestamp from the sample
    assert any(code["code"] == "timeStamp.validated" for code in result.validation_codes["success"])


def test_tampered_media_is_invalid_with_the_failure_recorded(fixtures: FixtureSet) -> None:
    result = read_manifest_store(fixtures.c2pa_tampered)
    assert result.status == "invalid"
    assert result.validation_state == "Invalid"
    failures = [code["code"] for code in result.validation_codes["failure"]]
    assert "assertion.dataHash.mismatch" in failures
    assert result.manifest_count == 1  # the manifest still parses; its hashes do not match


def test_multiple_manifests_are_summarised(fixtures: FixtureSet) -> None:
    result = read_manifest_store(fixtures.c2pa_multi_manifest)
    assert result.status == "valid"
    assert result.manifest_count == 2
    assert result.active_manifest in [m.label for m in result.manifests]
    generators = {m.claim_generator for m in result.manifests}
    assert "Vestigo Test Fixture 1.0" in generators
    assert "Vestigo Test Fixture Second Pass 1.0" in generators
    active = next(m for m in result.manifests if m.label == result.active_manifest)
    assert active.ingredient_count == 1


def test_media_without_c2pa_is_absent(fixtures: FixtureSet) -> None:
    for name in ("jpeg", "png", "video_scenes", "audio_wav"):
        result = read_manifest_store(getattr(fixtures, name))
        assert result.status == "absent", name
        assert result.manifest_count == 0
        assert result.raw_report is None
        assert result.error is None


def test_unsupported_container_is_unverifiable(fixtures: FixtureSet) -> None:
    result = read_manifest_store(fixtures.video_mkv)
    assert result.status == "unverifiable"
    assert result.error and "unsupported format" in result.error
