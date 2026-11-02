"""Milestone 1 image pipeline (`image.v1`). Stages run in the order of IMAGE_STAGES."""

from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageFailure, StageOutput
from app.schemas.common import EvidenceClassification, MediaType
from app.schemas.evidence import StageError
from app.services.hashing import hash_file, hashlib_version
from app.services.metadata import EXIFTOOL_ARGS, extract_metadata

IMAGE_PIPELINE = "image.v1"


class HashesStage(AnalysisStage):
    name = "hashes"
    media_type = MediaType.IMAGE
    method = (
        "SHA-256 and MD5 computed over the stored original's bytes and compared with the values "
        "recorded when the file was uploaded."
    )
    classification = EvidenceClassification.DERIVED
    source = "artifact:original"
    tool_name = "hashlib"
    limitations = (
        "Hashes identify this exact sequence of bytes. Any re-save, crop, or metadata change produces "
        "different hashes, even when the image looks the same.",
        "MD5 is included for compatibility with other tools. It is not collision-resistant and should "
        "not be relied on alone.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return hashlib_version()

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        hashes = hash_file(artifact.path)
        matches = (hashes.sha256, hashes.md5, hashes.size_bytes) == (
            artifact.sha256,
            artifact.md5,
            artifact.size_bytes,
        )
        data = {
            "sha256": hashes.sha256,
            "md5": hashes.md5,
            "size_bytes": hashes.size_bytes,
            "matches_upload_record": matches,
        }
        if not matches:
            raise StageFailure(
                "INTEGRITY_MISMATCH",
                "The stored file no longer matches the hashes recorded at upload.",
                data,
            )
        return StageOutput(data)


class MetadataStage(AnalysisStage):
    name = "metadata"
    media_type = MediaType.IMAGE
    method = (
        f"ExifTool reads the metadata embedded in the file (exiftool {' '.join(EXIFTOOL_ARGS)}). Tags are "
        "grouped by ExifTool group; a tag that repeats within a group keeps its copy number."
    )
    classification = EvidenceClassification.OBSERVED
    source = "artifact:original"
    tool_name = "ExifTool"
    option = "metadata"
    limitations = (
        "Embedded metadata is easy to edit, add, or remove. Values are reported as written in the file "
        "and are not verified.",
        "Missing metadata is common (many platforms strip it) and is not evidence of anything by itself.",
        "Composite tags are calculated by ExifTool from other tags; they are not stored in the file.",
        "File-system attributes (name, dates, permissions) describe Vestigo's stored copy, not the "
        "uploaded file, and are left out.",
        "GPS values, if present, are shown as written. Milestone 1 performs no location analysis.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return ctx.tools.require("exiftool").version or "unknown"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        tool = ctx.tools.require("exiftool")
        result = extract_metadata(tool, artifact.path, ctx.settings.tool_timeout_seconds)
        ctx.derived.write(self.name, "exiftool_json", "exiftool.json", result.raw_output)
        warnings = [StageError(type="EXIFTOOL_ERROR", message=text) for text in result.parsed.errors]
        warnings += [StageError(type="EXIFTOOL_WARNING", message=text) for text in result.parsed.warnings]
        return StageOutput(data=result.parsed.sections, warnings=warnings)


IMAGE_STAGES: tuple[AnalysisStage, ...] = (HashesStage(), MetadataStage())
