import shutil
from pathlib import Path

import pytest

from app.core.tools import ToolRegistry, ToolStatus
from app.services.metadata import extract_metadata, parse_exiftool_record
from tests.fixtures.make_fixtures import FixtureSet


@pytest.fixture(scope="module")
def exiftool() -> ToolStatus:
    return ToolRegistry().require("exiftool")


def all_groups(sections: dict) -> set[str]:
    return {group for section in sections.values() for group in section}


def test_exif_xmp_and_iptc_are_extracted_into_their_sections(
    exiftool: ToolStatus, fixtures: FixtureSet
) -> None:
    result = extract_metadata(exiftool, fixtures.with_metadata, timeout=30)
    sections = result.parsed.sections

    assert sections["exif"]["IFD0"]["Make"] == "VestigoTestCam"
    assert sections["exif"]["ExifIFD"]["DateTimeOriginal"] == "2026:01:15 10:30:00"
    assert sections["exif"]["GPS"]["GPSLatitudeRef"] == "North"
    assert sections["xmp"]["XMP-dc"]["Title"] == "Fixture title"
    assert sections["iptc"]["IPTC"]["City"] == "Testville"
    assert "ImageSize" in sections["composite"]["Composite"]
    assert result.parsed.warnings == []
    assert result.raw_output.lstrip().startswith(b"[")


def test_stored_copy_attributes_are_left_out(exiftool: ToolStatus, fixtures: FixtureSet) -> None:
    sections = extract_metadata(exiftool, fixtures.with_metadata, timeout=30).parsed.sections

    assert "System" not in all_groups(sections)
    assert "File" in sections["other"]
    assert "FileName" not in sections["other"]["File"]
    assert "Directory" not in str(sections)


def test_file_without_metadata_returns_empty_sections(exiftool: ToolStatus, fixtures: FixtureSet) -> None:
    parsed = extract_metadata(exiftool, fixtures.png, timeout=30).parsed

    assert parsed.sections["exif"] == {}
    assert parsed.sections["xmp"] == {}
    assert parsed.sections["iptc"] == {}
    assert parsed.warnings == []


def test_corrupt_metadata_is_reported_as_a_warning(exiftool: ToolStatus, fixtures: FixtureSet) -> None:
    parsed = extract_metadata(exiftool, fixtures.corrupt_exif, timeout=30).parsed

    assert any("IFD0" in warning for warning in parsed.warnings)


def test_copy_numbers_are_kept_only_for_tags_repeated_within_a_group() -> None:
    parsed = parse_exiftool_record(
        {
            "SourceFile": "/data/x.jpg",
            "ExifTool:ExifToolVersion": 13.25,
            "ExifTool:Warning": "Something odd",
            "File:System:FileName": "x.jpg",
            "EXIF:GPS:Copy1:GPSLatitude": "51 deg",
            "Composite:GPSLatitude": "51 deg N",
            "JUMBF:JUMDLabel": "c2pa",
            "JUMBF:Copy1:JUMDLabel": "c2pa.claim",
            "ICC_Profile:ICC-header:ProfileVersion": "2.1.0",
        }
    )

    assert parsed.sections["exif"] == {"GPS": {"GPSLatitude": "51 deg"}}
    assert parsed.sections["composite"] == {"Composite": {"GPSLatitude": "51 deg N"}}
    assert parsed.sections["other"]["JUMBF"] == {"JUMDLabel": "c2pa", "JUMDLabel (Copy1)": "c2pa.claim"}
    assert parsed.sections["other"]["ICC_Profile:ICC-header"] == {"ProfileVersion": "2.1.0"}
    assert parsed.warnings == ["Something odd"]
    assert "System" not in all_groups(parsed.sections)


def fake_tool(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path


def registry_with(fakes: dict[str, Path | None]) -> ToolRegistry:
    def which(name: str) -> str | None:
        if name in fakes:
            fake = fakes[name]
            return str(fake) if fake else None
        return shutil.which(name)

    return ToolRegistry(which=which)


def test_tool_registry_reports_fake_tool_versions(tmp_path: Path) -> None:
    exiftool = fake_tool(tmp_path, "exiftool", 'echo "99.1"')
    assert registry_with({"exiftool": exiftool}).require("exiftool").version == "99.1"
