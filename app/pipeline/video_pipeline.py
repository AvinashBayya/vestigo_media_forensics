"""Milestone 3 video pipeline (`video.v1`). Stages run in the order of VIDEO_STAGES.

The hashes and metadata stages are the image pipeline's, bound to video; media_info is video-only.
Later stages (scene detection, keyframes, keyframe pHash, keyframe OCR, duplicate search) are added
step by step per 13-MILESTONE-3-PLAN.md §11.
"""

from dataclasses import asdict

from PIL import Image
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import __version__
from app.core.tools import ToolError
from app.models import EvidenceRecord, KeyframeFingerprint
from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageFailure, StageOutput
from app.pipeline.image_pipeline import HashesStage, LocationCluesStage, MetadataStage
from app.schemas.common import EvidenceClassification, MediaType
from app.schemas.evidence import StageError
from app.services import media_info
from app.services.c2pa import (
    C2PA_LIMITATIONS,
    c2pa_validator_version,
    manifest_payload,
    read_manifest_store,
)
from app.services.duplicates import FrameHash, find_matches
from app.services.keyframes import (
    DEDUPE_SECONDS,
    JPEG_QUALITY,
    MIN_KEYFRAMES,
    OCR_KEYFRAME_LIMIT,
    THUMBNAIL_MAX_SIDE,
    evenly_spaced_subset,
    extract_keyframe,
    select_keyframes,
)
from app.services.ocr import LANGUAGES, PAGE_SEGMENTATION_MODE, pillow_version, run_ocr
from app.services.phash import (
    BITS,
    FINGERPRINT_ALGORITHM,
    compute_orientation_phashes,
    imagehash_version,
)
from app.services.scenes import SceneChange, detect_scene_changes
from app.services.validation import InvalidVideoError, probe_video

VIDEO_PIPELINE = "video.v1"


class VideoHashesStage(HashesStage):
    media_type = MediaType.VIDEO
    limitations = (
        "Hashes identify this exact sequence of bytes. Any re-encode, trim, remux, or metadata change "
        "produces different hashes, even when the video looks the same.",
        "MD5 is included for compatibility with other tools. It is not collision-resistant and should "
        "not be relied on alone.",
    )


class VideoMetadataStage(MetadataStage):
    media_type = MediaType.VIDEO


class MediaInfoStage(AnalysisStage):
    name = "media_info"
    media_type = MediaType.VIDEO
    method = (
        "ffprobe reads the container and stream headers (ffprobe -print_format json -show_format "
        "-show_streams) and the values are reported as written: container format, container-reported "
        "duration, and per-stream codec, profile, dimensions, frame rate, bit rate, sample rate, and "
        "channels. Nothing is decoded."
    )
    classification = EvidenceClassification.OBSERVED
    source = "artifact:original"
    tool_name = "ffprobe"
    limitations = (
        "Values come from container and stream headers as written. They are easy to edit and are not "
        "verified against the decoded media.",
        "Duration, frame rate, and bit rates are container-reported, not measured by decoding the file.",
        "Audio streams are inspected from their headers only. No audio is decoded, transcribed, or "
        "identified.",
        "Missing or sparse technical metadata is common and is not evidence of anything by itself.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return ctx.tools.require("ffprobe").version or "unknown"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        tool = ctx.tools.require("ffprobe")
        try:
            probe = probe_video(tool, artifact.path, ctx.settings.tool_timeout_seconds)
        except InvalidVideoError as exc:
            raise StageFailure("FFPROBE_ERROR", f"ffprobe could not read the stored file: {exc}.") from None
        ctx.derived.write(self.name, "ffprobe_json", "ffprobe.json", probe.raw_output)
        return StageOutput(media_info.summarize(probe.data))


class VideoC2PAStage(AnalysisStage):
    name = "c2pa"
    media_type = MediaType.VIDEO
    method = (
        "The file's C2PA manifest store is read and validated locally with the c2pa-python SDK: "
        "manifest hashes, claim signatures, and timestamps are checked, and each manifest's claim "
        "generator, signer certificate details, and assertions are summarised. No trust list is "
        "configured and no network is used. Containers the validator does not support are reported "
        "as unverifiable."
    )
    classification = EvidenceClassification.OBSERVED
    source = "artifact:original"
    tool_name = "c2pa-python"
    option = "c2pa"
    limitations = C2PA_LIMITATIONS

    def tool_version(self, ctx: StageContext) -> str:
        return f"{c2pa_validator_version()}; Vestigo {__version__}"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        read = read_manifest_store(artifact.path)
        if read.raw_report is not None:
            ctx.derived.write(self.name, "c2pa_manifest_store", "manifest_store.json", read.raw_report)
        return StageOutput(
            {
                "present": read.manifest_count > 0,
                "manifest_labels": [manifest.label for manifest in read.manifests],
                "details": {},
                **manifest_payload(read),
            }
        )


class VideoLocationCluesStage(LocationCluesStage):
    """Same reader as images (M6): container location tags (ISO 6709) land here as written."""

    media_type = MediaType.VIDEO


class SceneChangesStage(AnalysisStage):
    name = "scene_changes"
    media_type = MediaType.VIDEO
    method = (
        "ffmpeg's scene filter (select='gt(scene,threshold)') compares each decoded frame with the "
        "previous one and scores how different they are, from 0 to 1. Frames scoring above the "
        "threshold are listed with their presentation timestamps. The raw filter output is kept as a "
        "derived file."
    )
    classification = EvidenceClassification.DERIVED
    source = "artifact:original"
    tool_name = "ffmpeg"
    option = "scene_detection"
    limitations = (
        "The score is a frame-difference measure. Gradual transitions such as dissolves or fades may "
        "score below the threshold and be missed, and fast motion or flashes can score above it "
        "without a cut.",
        "Scene changes are ordinary editing. They say nothing about whether the video is manipulated "
        "or deceptive.",
        "Timestamps are presentation times from decoding and can differ slightly between players.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return ctx.tools.require("ffmpeg").version or "unknown"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        tool = ctx.tools.require("ffmpeg")
        threshold = ctx.settings.scene_threshold
        result = detect_scene_changes(
            tool, artifact.path, threshold, ctx.scratch_dir, ctx.settings.video_timeout_seconds
        )
        ctx.derived.write(self.name, "ffmpeg_scene_output", "ffmpeg.txt", result.raw_output)
        return StageOutput(
            {
                "threshold": threshold,
                "count": len(result.changes),
                "changes": [{"time": change.time, "score": change.score} for change in result.changes],
            }
        )


class KeyframesStage(AnalysisStage):
    name = "keyframes"
    media_type = MediaType.VIDEO
    method = (
        "Representative frames are selected deterministically: the first decodable frame, one frame "
        "per detected scene change (highest scores kept when over the keyframe limit), and evenly "
        f"spaced frames to reach at least {MIN_KEYFRAMES} when fewer were found; candidates within "
        f"{DEDUPE_SECONDS:g} s of a selected frame are dropped. Each frame is extracted with ffmpeg "
        f"(one decoded frame at its timestamp, display rotation applied) as a JPEG capped at "
        f"{THUMBNAIL_MAX_SIDE} px on the longest side (quality {JPEG_QUALITY}). Every frame records "
        "its timestamp and why it was selected."
    )
    classification = EvidenceClassification.DERIVED
    source = "artifact:original + stage:scene_changes"
    tool_name = "ffmpeg"
    limitations = (
        "Keyframes are a bounded sample of the video. Content between the selected frames is not "
        "shown or analysed.",
        "Extracted frames are re-encoded, possibly downscaled JPEG copies for analysis and display, "
        "not original frames.",
        "When scene detection is disabled or finds nothing, frames are sampled at even intervals and "
        "can miss short shots entirely.",
        "Timestamps are presentation times from decoding and can differ slightly between players.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return ctx.tools.require("ffmpeg").version or "unknown"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        tool = ctx.tools.require("ffmpeg")
        duration = artifact.duration_seconds or 0.0
        scenes_result = ctx.results.get("scene_changes")
        scene_changes = []
        if scenes_result is not None and scenes_result.has_output:
            scene_changes = [
                SceneChange(change["time"], change["score"])
                for change in scenes_result.output.get("changes", [])
            ]
        selected = select_keyframes(duration, scene_changes, ctx.settings.max_keyframes)

        frames, warnings = [], []
        for frame in selected:
            scratch_file = ctx.scratch_dir / f"kf_{frame.seq:04d}.jpg"
            ok = extract_keyframe(
                tool, artifact.path, frame.timestamp, scratch_file, ctx.settings.video_timeout_seconds
            )
            if not ok:
                warnings.append(
                    StageError(
                        type="KEYFRAME_EXTRACTION_FAILED",
                        message=f"No frame could be extracted at {frame.timestamp:.3f} s.",
                    )
                )
                continue
            data = scratch_file.read_bytes()
            info = ctx.derived.write(
                self.name, "keyframe_jpeg", f"{frame.seq:04d}_t{frame.timestamp:.3f}.jpg", data
            )
            with Image.open(scratch_file) as thumbnail:
                width, height = thumbnail.size
            frames.append(
                {
                    "seq": frame.seq,
                    "timestamp": frame.timestamp,
                    "reason": frame.reason,
                    "scene_score": frame.scene_score,
                    "derived_file_id": info.derived_file_id,
                    "width": width,
                    "height": height,
                }
            )
        if not frames:
            raise StageFailure(
                "KEYFRAME_EXTRACTION_FAILED",
                "No keyframes could be extracted from the video.",
                {"requested": len(selected)},
            )
        return StageOutput(
            {
                "policy": {
                    "min_keyframes": MIN_KEYFRAMES,
                    "max_keyframes": ctx.settings.max_keyframes,
                    "dedupe_seconds": DEDUPE_SECONDS,
                    "thumbnail_max_side": THUMBNAIL_MAX_SIDE,
                },
                "requested": len(selected),
                "extracted": len(frames),
                "frames": frames,
            },
            warnings=warnings,
        )


class KeyframePHashStage(AnalysisStage):
    name = "keyframe_phash"
    media_type = MediaType.VIDEO
    method = (
        "64-bit perceptual hash (pHash) of each extracted keyframe: the frame is converted to "
        "greyscale and reduced to 32x32 pixels; a discrete cosine transform is applied and each of "
        "the 8x8 lowest-frequency coefficients is compared with their median. The hashes feed "
        "duplicate search across videos and images."
    )
    classification = EvidenceClassification.DERIVED
    source = "stage:keyframes"
    tool_name = "imagehash"
    depends_on = ("keyframes",)
    limitations = (
        "A perceptual hash summarises coarse visual structure. Similar hashes mean similar-looking "
        "frames, not a shared source or history.",
        "Only the selected keyframes are hashed. Content between them is not represented.",
        "It tolerates re-encoding and resizing but not significant crops or heavy edits. Rotated "
        "and mirrored copies are found through separately computed variant hashes in duplicate "
        "search, not by the hash itself.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return imagehash_version()

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        keyframes = ctx.results["keyframes"].output
        frames = []
        for frame in keyframes.get("frames", []):
            path = ctx.derived.stored_file("keyframes", f"{frame['seq']:04d}_t{frame['timestamp']:.3f}.jpg")
            result = compute_orientation_phashes(path)
            frames.append(
                {
                    "seq": frame["seq"],
                    "timestamp": frame["timestamp"],
                    "value": result.value,
                    # Rotated and mirrored variants (D19), used by duplicate search only; the
                    # fingerprint index keeps the canonical value.
                    "orientations": result.variants,
                    "derived_file_id": frame["derived_file_id"],
                }
            )
        return StageOutput({"algorithm": "pHash", "bits": BITS, "count": len(frames), "frames": frames})

    def on_recorded(self, record: EvidenceRecord, session: Session) -> None:
        # The keyframe fingerprint index holds the artifact's most recent successful hashes.
        if record.status not in ("succeeded", "partial") or not record.payload.get("frames"):
            return
        session.execute(
            delete(KeyframeFingerprint).where(
                KeyframeFingerprint.artifact_id == record.artifact_id,
                KeyframeFingerprint.algorithm == FINGERPRINT_ALGORITHM,
            )
        )
        for frame in record.payload["frames"]:
            session.add(
                KeyframeFingerprint(
                    artifact_id=record.artifact_id,
                    algorithm=FINGERPRINT_ALGORITHM,
                    frame_seq=frame["seq"],
                    timestamp_seconds=frame["timestamp"],
                    value_hex=frame["value"],
                    evidence_id=record.id,
                    derived_file_id=frame["derived_file_id"],
                    created_at=record.completed_at,
                )
            )


class KeyframeOCRStage(AnalysisStage):
    name = "keyframe_ocr"
    media_type = MediaType.VIDEO
    method = (
        f"Tesseract OCR (languages: {'+'.join(LANGUAGES)}; --psm {PAGE_SEGMENTATION_MODE}) runs on an "
        f"evenly spaced subset of at most {OCR_KEYFRAME_LIMIT} extracted keyframes, always including "
        "the first and last. Each frame uses the two-pass preprocessing of the image OCR stage "
        "(grayscale with upscaling, and an adaptive-threshold pass, the better pass chosen by the "
        "recorded rule); raw Tesseract TSV output is stored per analysed frame and pass. The prepared "
        "pass images are not stored for keyframes; the keyframe thumbnails themselves are."
    )
    classification = EvidenceClassification.DERIVED
    source = "stage:keyframes"
    tool_name = "Tesseract"
    depends_on = ("keyframes",)
    option = "keyframe_ocr"
    limitations = (
        "OCR output is provisional, best-effort text, not a verified transcription (decision D14). "
        "Text can be missed or misread; check it against the frames.",
        "Only a bounded subset of keyframes is analysed. Text shown between the analysed frames, or "
        "in unselected parts of the video, is not read.",
        "English language data only. Text in other languages or scripts may be missed or misread.",
        "Confidence is Tesseract's own estimate, not a measured accuracy.",
        "Small, moving, stylised, or low-contrast captions are often misread or missed.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        version = ctx.tools.require("tesseract").version or "unknown"
        return f"{version}; Pillow {pillow_version()}"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        tool = ctx.tools.require("tesseract")
        keyframes = ctx.results["keyframes"].output.get("frames", [])
        chosen = [keyframes[index] for index in evenly_spaced_subset(len(keyframes), OCR_KEYFRAME_LIMIT)]
        frames, warnings = [], []
        for frame in chosen:
            path = ctx.derived.stored_file("keyframes", f"{frame['seq']:04d}_t{frame['timestamp']:.3f}.jpg")
            scratch = ctx.scratch_dir / f"ocr_{frame['seq']:04d}"
            scratch.mkdir(exist_ok=True)
            try:
                result = run_ocr(tool, path, scratch, ctx.settings.ocr_timeout_seconds)
            except ToolError as exc:
                warnings.append(
                    StageError(
                        type="OCR_FRAME_FAILED",
                        message=f"OCR failed on the keyframe at {frame['timestamp']:.3f} s: {exc}",
                    )
                )
                continue
            for ocr_pass in result.passes:
                if ocr_pass.recognition is not None:
                    ctx.derived.write(
                        self.name,
                        f"tesseract_tsv_{ocr_pass.variant}",
                        f"{frame['seq']:04d}.{ocr_pass.variant}.tsv",
                        ocr_pass.recognition.tsv,
                        # Lineage (M4B): the TSV was read from this keyframe thumbnail, not the original.
                        source_derived_file_id=frame["derived_file_id"],
                    )
            if result.variant_error is not None:
                warnings.append(
                    StageError(
                        type="OCR_VARIANT_FAILED",
                        message=(
                            f"The threshold pass failed on the keyframe at {frame['timestamp']:.3f} s; "
                            f"the grayscale pass is used. {result.variant_error}"
                        ),
                    )
                )
            payload = result.payload()
            frames.append(
                {
                    "seq": frame["seq"],
                    "timestamp": frame["timestamp"],
                    **{
                        key: payload[key]
                        for key in (
                            "text",
                            "cleaned_text",
                            "cleaning",
                            "confidence",
                            "word_count",
                            "preprocessing",
                            "candidates",
                            "selected",
                        )
                    },
                }
            )
        if chosen and not frames:
            raise StageFailure("OCR_FRAME_FAILED", "OCR failed on every analysed keyframe.", {"analyzed": 0})
        return StageOutput(
            {
                "engine": "tesseract",
                "languages": list(LANGUAGES),
                "frame_limit": OCR_KEYFRAME_LIMIT,
                "analyzed": len(frames),
                "frames": frames,
            },
            warnings=warnings,
        )


class VideoDuplicatesStage(AnalysisStage):
    name = "duplicates"
    media_type = MediaType.VIDEO
    method = (
        "Compares each keyframe's pHash — and its rotated (90/180/270 degrees) and mirrored "
        "variants — with the stored pHash of every other image and with the keyframe pHashes of "
        "every analysed video in the local library using Hamming distance. Artifacts with a hash at "
        "or below the threshold are listed with, per matching keyframe, its best counterpart, that "
        "pair's distance, and which orientation matched. Byte-identical files are found by SHA-256. "
        "Artifacts the analyst excluded from duplicate search are not compared; their number is "
        "recorded."
    )
    classification = EvidenceClassification.DERIVED
    source = "stage:keyframe_phash + local library"
    tool_name = "Vestigo duplicate search"
    depends_on = ("keyframe_phash",)
    option = "duplicate_search"
    limitations = (
        "Searches only the artifacts in this local Vestigo library, as it was when the job ran. No "
        "external or online search is performed.",
        "Only the selected keyframes are compared. Two videos sharing content between keyframes, or "
        "sharing shots that keyframe selection skipped, can be missed.",
        "Artifacts that have not been analysed have no perceptual hashes and are found only if they "
        "are byte-identical.",
        "A match means frames look alike at a coarse level. It does not show which came first or that "
        "one was derived from the other.",
        "Artifacts excluded from duplicate search by the analyst are not compared, even if identical. "
        "`excluded_count` records how many were left out.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return __version__

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        threshold = ctx.settings.phash_max_distance
        own_hashes = [
            FrameHash(frame["value"], frame["seq"], frame["timestamp"], frame.get("orientations"))
            for frame in ctx.results["keyframe_phash"].output.get("frames", [])
        ]
        library = ctx.library.snapshot(artifact.id, FINGERPRINT_ALGORITHM)
        search = find_matches(artifact.sha256, own_hashes, library.entries, threshold)
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


VIDEO_STAGES: tuple[AnalysisStage, ...] = (
    VideoHashesStage(),
    MediaInfoStage(),
    VideoMetadataStage(),
    VideoC2PAStage(),
    VideoLocationCluesStage(),
    SceneChangesStage(),
    KeyframesStage(),
    KeyframePHashStage(),
    KeyframeOCRStage(),
    VideoDuplicatesStage(),
)
