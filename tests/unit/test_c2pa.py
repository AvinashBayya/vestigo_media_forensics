import pytest

from app.core.tools import ToolRegistry, ToolStatus
from app.services.c2pa import C2PA_TIFF_TAG, detect_c2pa, scan_bytes
from tests.fixtures.make_fixtures import (
    FixtureSet,
    c2pa_jumbf_box,
    png_with_chunk,
    tiff_with_tag,
    webp_with_chunk,
)

SAMPLE_MANIFEST = "contentauth:urn:uuid:4d971750-1db4-4492-a87c-5c3e7ed33efc"


@pytest.fixture(scope="module")
def exiftool() -> ToolStatus:
    return ToolRegistry().require("exiftool")


@pytest.mark.parametrize(
    ("fixture_name", "mime_type"),
    [("jpeg", "image/jpeg"), ("png", "image/png"), ("webp", "image/webp"), ("tiff", "image/tiff")],
)
def test_files_without_c2pa_are_reported_as_not_present(
    exiftool: ToolStatus, fixtures: FixtureSet, fixture_name: str, mime_type: str
) -> None:
    detection = detect_c2pa(exiftool, getattr(fixtures, fixture_name), mime_type, timeout=30)

    assert detection.present is False
    assert detection.manifest_labels == []
    assert detection.warnings == []
    assert detection.details["detectors"]["byte_scan"]["found"] is False
    assert detection.details["detectors"]["exiftool"]["found"] is False


def test_c2pa_sample_is_detected_with_its_manifest(exiftool: ToolStatus, fixtures: FixtureSet) -> None:
    detection = detect_c2pa(exiftool, fixtures.c2pa, "image/jpeg", timeout=30)

    assert detection.present is True
    assert detection.manifest_labels == [SAMPLE_MANIFEST]
    assert detection.warnings == []
    detectors = detection.details["detectors"]
    assert detectors["byte_scan"]["found"] is True
    assert detectors["byte_scan"]["container"] == "jpeg_app11"
    assert detectors["byte_scan"]["segments"] >= 1
    assert detectors["exiftool"]["found"] is True

    manifest = detection.details["manifests"][0]
    assert manifest["claim"]["Claim_generator"] == "make_test_images/0.16.1 c2pa-rs/0.16.1"
    assert manifest["claim"]["Title"] == "C.jpg"
    assert "c2pa.actions" in manifest["assertions"]
    assert manifest["signature_present"] is True
    assert detection.details["active_manifest_label"] == SAMPLE_MANIFEST


def test_malformed_c2pa_does_not_crash_and_is_reported(exiftool: ToolStatus, fixtures: FixtureSet) -> None:
    detection = detect_c2pa(exiftool, fixtures.invalid_c2pa, "image/jpeg", timeout=30)

    assert detection.details["detectors"]["byte_scan"]["found"] is True
    assert detection.details["detectors"]["exiftool"]["found"] is False
    assert any("JUMBF" in warning for warning in detection.warnings)
    assert any("disagree" in warning for warning in detection.warnings)


def test_byte_scan_finds_c2pa_in_png_webp_and_tiff(fixtures: FixtureSet) -> None:
    box = c2pa_jumbf_box()

    png = scan_bytes(png_with_chunk(fixtures.png.read_bytes(), b"caBX", box), "image/png")
    webp = scan_bytes(webp_with_chunk(fixtures.webp.read_bytes(), b"C2PA", box), "image/webp")
    tiff = scan_bytes(tiff_with_tag(C2PA_TIFF_TAG, box), "image/tiff")

    for scan, container in ((png, "png_caBX"), (webp, "webp_C2PA"), (tiff, "tiff_tag_52545")):
        assert scan.found is True, container
        assert scan.container == container
        assert scan.segments == 1
        assert scan.problems == []


def test_byte_scan_reports_a_chunk_that_is_not_c2pa(fixtures: FixtureSet) -> None:
    scan = scan_bytes(png_with_chunk(fixtures.png.read_bytes(), b"caBX", b"not a jumbf box"), "image/png")

    assert scan.found is False
    assert scan.problems


def test_byte_scan_tolerates_garbage() -> None:
    for mime_type in ("image/jpeg", "image/png", "image/webp", "image/tiff"):
        scan = scan_bytes(b"\xff\xd8\xff" + b"\x00" * 3, mime_type)
        assert scan.found is False
