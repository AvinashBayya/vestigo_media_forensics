"""Milestone 1 image pipeline (`image.v1`). Stages run in the order of IMAGE_STAGES."""

from dataclasses import asdict

from sqlalchemy.orm import Session

from app import __version__
from app.models import EvidenceRecord, ImageFingerprint
from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageFailure, StageOutput
from app.schemas.common import EvidenceClassification, MediaType
from app.schemas.evidence import StageError
from app.services.c2pa import detect_c2pa
from app.services.duplicates import find_matches
from app.services.hashing import hash_file, hashlib_version
from app.services.metadata import EXIFTOOL_ARGS, extract_metadata
from app.services.ocr import LANGUAGES, PAGE_SEGMENTATION_MODE, run_ocr
from app.services.phash import BITS, FINGERPRINT_ALGORITHM, compute_phash, imagehash_version

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


class C2PAStage(AnalysisStage):
    name = "c2pa"
    media_type = MediaType.IMAGE
    method = (
        "Detection only. A byte-level scan of the file container (JPEG APP11 segments, PNG caBX chunks, "
        "WebP C2PA chunks, TIFF tag 52545) looks for a JUMBF box of type 'c2pa', and ExifTool decodes "
        "any JUMBF boxes and the claim data inside them. The two checks are reported separately."
    )
    classification = EvidenceClassification.OBSERVED
    source = "artifact:original"
    tool_name = "ExifTool + Vestigo byte-level scan"
    option = "c2pa"
    limitations = (
        "Detection only: signatures, certificate chains, timestamps, and hash bindings are NOT validated "
        "in Milestone 1. A detected manifest may be invalid, altered, or signed by an untrusted party.",
        "A detected manifest is not proof that the content is authentic or that its claims are true.",
        "Absence of a manifest is normal (most images have none, and many platforms remove them) and "
        "proves nothing.",
        "Manifests stored outside the file and referenced from XMP are not fetched; no network access "
        "is used.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return f"ExifTool {ctx.tools.require('exiftool').version}; Vestigo {__version__}"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        tool = ctx.tools.require("exiftool")
        detection = detect_c2pa(tool, artifact.path, artifact.mime_type, ctx.settings.tool_timeout_seconds)
        ctx.derived.write(self.name, "exiftool_c2pa_json", "exiftool.json", detection.raw_output)
        return StageOutput(
            {
                "present": detection.present,
                "validation_performed": False,
                "manifest_labels": detection.manifest_labels,
                "details": detection.details,
            },
            warnings=[StageError(type="C2PA_STRUCTURE_WARNING", message=text) for text in detection.warnings],
        )


class PerceptualHashStage(AnalysisStage):
    name = "perceptual_hash"
    media_type = MediaType.IMAGE
    method = (
        "64-bit perceptual hash (pHash): the image, turned upright using its EXIF orientation, is "
        "converted to greyscale and reduced to 32x32 pixels; a discrete cosine transform is applied and "
        "each of the 8x8 lowest-frequency coefficients is compared with their median."
    )
    classification = EvidenceClassification.DERIVED
    source = "artifact:original"
    tool_name = "imagehash"
    limitations = (
        "A perceptual hash summarises coarse visual structure. Similar hashes mean similar-looking "
        "images, not a shared source or history.",
        "It tolerates resizing and recompression but not significant crops, rotations (other than EXIF "
        "orientation), mirroring, or heavy edits.",
        "Transparency is ignored. Animated or multi-page images are hashed from the first frame only.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return imagehash_version()

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        result = compute_phash(artifact.path)
        return StageOutput(
            {
                "algorithm": "pHash",
                "bits": BITS,
                "value": result.value,
                "frames": result.frames,
                "normalization": result.normalization,
            }
        )

    def on_recorded(self, record: EvidenceRecord, session: Session) -> None:
        # The fingerprint index keeps the artifact's most recent successful hash.
        if record.status in ("succeeded", "partial") and record.payload.get("value"):
            session.merge(
                ImageFingerprint(
                    artifact_id=record.artifact_id,
                    algorithm=FINGERPRINT_ALGORITHM,
                    value_hex=record.payload["value"],
                    evidence_id=record.id,
                    created_at=record.completed_at,
                )
            )


class OCRStage(AnalysisStage):
    name = "ocr"
    media_type = MediaType.IMAGE
    method = (
        f"Tesseract OCR (languages: {'+'.join(LANGUAGES)}; automatic page segmentation, "
        f"--psm {PAGE_SEGMENTATION_MODE}) run on an upright PNG copy of the image. Confidence is the mean "
        "of Tesseract's per-word confidence scores, on a 0-1 scale."
    )
    classification = EvidenceClassification.DERIVED
    source = "artifact:original"
    tool_name = "Tesseract"
    option = "ocr"
    limitations = (
        "English language data only in Milestone 1. Text in other languages or scripts may be missed or "
        "misread.",
        "Handwriting, stylised fonts, small or low-contrast text, and rotated or curved text are often "
        "misread or missed.",
        "Confidence is Tesseract's own estimate, not a measured accuracy. Check extracted text against "
        "the image.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return ctx.tools.require("tesseract").version or "unknown"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        tool = ctx.tools.require("tesseract")
        result = run_ocr(tool, artifact.path, ctx.scratch_dir, ctx.settings.ocr_timeout_seconds)
        ctx.derived.write(self.name, "tesseract_tsv", "tesseract.tsv", result.tsv)
        return StageOutput(
            {
                "engine": "tesseract",
                "languages": list(LANGUAGES),
                "text": result.text,
                "confidence": result.confidence,
                "word_count": result.word_count,
                "preprocessing": result.preprocessing,
            }
        )


class DuplicatesStage(AnalysisStage):
    name = "duplicates"
    media_type = MediaType.IMAGE
    method = (
        "Compares this image's pHash with the stored pHash of every other artifact in the local library "
        "using Hamming distance, and lists those at or below the threshold. Byte-identical files are "
        "found by SHA-256."
    )
    classification = EvidenceClassification.DERIVED
    source = "stage:perceptual_hash + local library"
    tool_name = "Vestigo duplicate search"
    depends_on = ("perceptual_hash",)
    option = "duplicate_search"
    limitations = (
        "Searches only the artifacts in this local Vestigo library, as it was when the job ran. No "
        "external or online search is performed.",
        "Artifacts that have not been analysed have no perceptual hash and are found only if they are "
        "byte-identical.",
        "A match means the images look alike at a coarse level. It does not show which came first or "
        "that one was derived from the other.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return __version__

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        threshold = ctx.settings.phash_max_distance
        own_hash = ctx.results["perceptual_hash"].output["value"]
        library = ctx.library.entries(artifact.id, FINGERPRINT_ALGORITHM)
        search = find_matches(artifact.sha256, own_hash, library, threshold)
        return StageOutput(
            {
                "algorithm": "pHash",
                "threshold": threshold,
                "library_size": search.library_size,
                "compared": search.compared,
                "matches": [asdict(match) for match in search.matches],
            }
        )


IMAGE_STAGES: tuple[AnalysisStage, ...] = (
    HashesStage(),
    MetadataStage(),
    C2PAStage(),
    PerceptualHashStage(),
    OCRStage(),
    DuplicatesStage(),
)
