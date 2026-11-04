"""Milestone 1 image pipeline (`image.v1`). Stages run in the order of IMAGE_STAGES."""

from dataclasses import asdict

from sqlalchemy.orm import Session

from app import __version__
from app.models import EvidenceRecord, ImageFingerprint
from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageFailure, StageOutput
from app.schemas.common import EvidenceClassification, MediaType
from app.schemas.evidence import StageError
from app.services.c2pa import detect_c2pa
from app.services.duplicates import FrameHash, find_matches
from app.services.hashing import hash_file, hashlib_version
from app.services.metadata import EXIFTOOL_ARGS, extract_metadata
from app.services.ocr import (
    LANGUAGES,
    MAX_UPSCALE_FACTOR,
    MIN_CONFIDENCE_GAIN,
    MIN_CONFIDENCE_WITHOUT_PASS_A_WORDS,
    MIN_WORD_RETENTION,
    PAGE_SEGMENTATION_MODE,
    UPSCALE_TARGET_SIDE,
    pillow_version,
    run_ocr,
)
from app.services.phash import (
    BITS,
    FINGERPRINT_ALGORITHM,
    compute_orientation_phashes,
    compute_phash,
    imagehash_version,
)

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
        "It tolerates resizing and recompression but not significant crops or heavy edits. Rotated "
        "and mirrored copies are found through separately computed variant hashes in duplicate "
        "search, not by the hash itself.",
        "Transparency is ignored. Animated or multi-page images are hashed from the first frame only.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return imagehash_version()

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        result = compute_phash(artifact.path)
        # Rotated and mirrored variants (D19) let duplicate search find reoriented copies. The
        # canonical value and the fingerprint index are unchanged.
        orientations = compute_orientation_phashes(artifact.path)
        return StageOutput(
            {
                "algorithm": "pHash",
                "bits": BITS,
                "value": result.value,
                "orientation_values": orientations.variants,
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
        f"--psm {PAGE_SEGMENTATION_MODE}) run twice on copies of the image, prepared with Pillow: "
        "(A) upright, greyscale, and upscaled up to "
        f"{MAX_UPSCALE_FACTOR}x (Lanczos) if the longest side allows it within {UPSCALE_TARGET_SIDE} px; "
        "(B) the same image after a local-mean adaptive threshold. Pass B is used only if it raises mean "
        f"confidence by at least {MIN_CONFIDENCE_GAIN:.2f} while keeping at least {MIN_WORD_RETENTION:.0%} "
        "of pass A's words, or, when pass A finds no words, if its mean confidence is at least "
        f"{MIN_CONFIDENCE_WITHOUT_PASS_A_WORDS:.2f}. Confidence is the mean of Tesseract's per-word "
        "confidence scores, on a 0-1 scale. Cleaned text removes only symbol-only lines and extra "
        "whitespace; the raw text is kept unchanged."
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
        "The choice between the two passes uses Tesseract's confidence, not measured accuracy. Upscaling "
        "can raise confidence while changing individual characters, so check numbers and names against "
        "the image.",
        "The adaptive threshold assumes dark text on a lighter background and can remove faint or "
        "light-on-dark text. Both passes are recorded so the discarded result can be checked.",
        "Cleaned text is cosmetic: it removes lines with no letters or digits and extra whitespace. The "
        "raw OCR text is kept unchanged.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        version = ctx.tools.require("tesseract").version or "unknown"
        return f"{version}; Pillow {pillow_version()}"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        tool = ctx.tools.require("tesseract")
        result = run_ocr(tool, artifact.path, ctx.scratch_dir, ctx.settings.ocr_timeout_seconds)
        for ocr_pass in result.passes:
            if ocr_pass.image_png:
                ctx.derived.write(
                    self.name, f"ocr_input_{ocr_pass.variant}", f"{ocr_pass.variant}.png", ocr_pass.image_png
                )
            if ocr_pass.recognition is not None:
                ctx.derived.write(
                    self.name,
                    f"tesseract_tsv_{ocr_pass.variant}",
                    f"{ocr_pass.variant}.tsv",
                    ocr_pass.recognition.tsv,
                )
        warnings = []
        if result.variant_error is not None:
            warnings.append(
                StageError(
                    type="OCR_VARIANT_FAILED",
                    message=f"The threshold pass failed; the grayscale pass is used. {result.variant_error}",
                )
            )
        return StageOutput(result.payload(), warnings=warnings)


class DuplicatesStage(AnalysisStage):
    name = "duplicates"
    media_type = MediaType.IMAGE
    method = (
        "Compares this image's pHash — and its rotated (90/180/270 degrees) and mirrored variants — "
        "with the stored pHash of every other image and with the keyframe pHashes of every analysed "
        "video in the local library using Hamming distance, and lists artifacts with a hash at or "
        "below the threshold, recording which orientation matched. Byte-identical files are found by "
        "SHA-256. Artifacts the analyst excluded from duplicate search are not compared; their number "
        "is recorded."
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
        "A match against a video lists the sampled keyframes this image resembles. Video content "
        "between keyframes is not searched.",
        "Artifacts excluded from duplicate search by the analyst are not compared, even if identical. "
        "`excluded_count` records how many were left out.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return __version__

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        threshold = ctx.settings.phash_max_distance
        phash_output = ctx.results["perceptual_hash"].output
        own_hash = FrameHash(phash_output["value"], variants=phash_output.get("orientation_values"))
        library = ctx.library.snapshot(artifact.id, FINGERPRINT_ALGORITHM)
        search = find_matches(artifact.sha256, [own_hash], library.entries, threshold)
        return StageOutput(
            {
                "algorithm": "pHash",
                "threshold": threshold,
                "library_size": search.library_size,
                "compared": search.compared,
                "excluded_count": library.excluded_count,
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
