"""Milestone 3 video pipeline (`video.v1`). Stages run in the order of VIDEO_STAGES.

The hashes and metadata stages are the image pipeline's, bound to video; media_info is video-only.
Later stages (scene detection, keyframes, keyframe pHash, keyframe OCR, duplicate search) are added
step by step per 13-MILESTONE-3-PLAN.md §11.
"""

from PIL import Image

from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageFailure, StageOutput
from app.pipeline.image_pipeline import HashesStage, MetadataStage
from app.schemas.common import EvidenceClassification, MediaType
from app.schemas.evidence import StageError
from app.services import media_info
from app.services.keyframes import (
    DEDUPE_SECONDS,
    JPEG_QUALITY,
    MIN_KEYFRAMES,
    THUMBNAIL_MAX_SIDE,
    extract_keyframe,
    select_keyframes,
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


VIDEO_STAGES: tuple[AnalysisStage, ...] = (
    VideoHashesStage(),
    MediaInfoStage(),
    VideoMetadataStage(),
    SceneChangesStage(),
    KeyframesStage(),
)
