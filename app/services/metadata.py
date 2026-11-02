"""Embedded metadata extraction with ExifTool."""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.tools import ToolError, ToolOutputError, ToolStatus, run_tool

# -G0:1:4 names every tag "family0:family1[:CopyN]:Tag"; -a keeps repeated tags; -struct keeps
# XMP structures as JSON objects instead of flattening them.
EXIFTOOL_ARGS = ("-json", "-G0:1:4", "-a", "-struct", "-charset", "filename=utf8")

SECTIONS = ("exif", "xmp", "iptc", "other", "composite")
_SECTION_BY_FAMILY0 = {"EXIF": "exif", "XMP": "xmp", "IPTC": "iptc", "Composite": "composite"}
# Attributes of Vestigo's stored copy (path, dates, permissions), not of the uploaded file.
_EXCLUDED_GROUPS = {("File", "System")}
_COPY = re.compile(r"Copy\d+")


@dataclass
class ParsedMetadata:
    sections: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=lambda: {name: {} for name in SECTIONS}
    )
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MetadataResult:
    parsed: ParsedMetadata
    raw_output: bytes


@dataclass(frozen=True)
class _Tag:
    family0: str
    family1: str
    copy: str | None
    name: str
    value: Any


def _split_key(key: str, value: Any) -> _Tag | None:
    parts = key.split(":")
    if len(parts) < 2:
        return None  # SourceFile
    groups, name = parts[:-1], parts[-1]
    copy = next((g for g in groups[1:] if _COPY.fullmatch(g)), None)
    family1 = next((g for g in groups[1:] if not _COPY.fullmatch(g)), groups[0])
    return _Tag(groups[0], family1, copy, name, value)


def parse_exiftool_record(record: dict[str, Any]) -> ParsedMetadata:
    tags = [tag for key, value in record.items() if (tag := _split_key(key, value)) is not None]
    # ExifTool numbers copies across the whole file; keep the number only when a tag really repeats
    # within its own group.
    occurrences = Counter((tag.family0, tag.family1, tag.name) for tag in tags)

    parsed = ParsedMetadata()
    for tag in tags:
        if tag.family0 == "ExifTool":
            if tag.name == "Warning":
                parsed.warnings.append(str(tag.value))
            elif tag.name == "Error":
                parsed.errors.append(str(tag.value))
            continue
        if (tag.family0, tag.family1) in _EXCLUDED_GROUPS:
            continue
        section = _SECTION_BY_FAMILY0.get(tag.family0, "other")
        if section == "other" and tag.family1 != tag.family0:
            group = f"{tag.family0}:{tag.family1}"
        else:
            group = tag.family1
        repeated = occurrences[(tag.family0, tag.family1, tag.name)] > 1
        name = f"{tag.name} ({tag.copy})" if repeated and tag.copy else tag.name
        parsed.sections[section].setdefault(group, {})[name] = tag.value
    return parsed


def run_exiftool_json(
    tool: ToolStatus, args: tuple[str, ...], path: Path, timeout: float
) -> tuple[dict, bytes]:
    completed = run_tool(tool, [*args, path], timeout=timeout)
    try:
        records = json.loads(completed.stdout or b"[]")
    except json.JSONDecodeError as exc:
        raise ToolOutputError("ExifTool returned output that is not valid JSON.") from exc
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        message = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        detail = message[0] if message else f"exit code {completed.returncode}"
        raise ToolError(f"ExifTool produced no metadata record ({detail}).")
    return records[0], completed.stdout


def extract_metadata(tool: ToolStatus, path: Path, timeout: float) -> MetadataResult:
    record, raw = run_exiftool_json(tool, EXIFTOOL_ARGS, path, timeout)
    return MetadataResult(parse_exiftool_record(record), raw)
