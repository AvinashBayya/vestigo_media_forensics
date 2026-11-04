"""Milestone 3 video pipeline (`video.v1`). Stages run in the order of VIDEO_STAGES.

The hashes and metadata stages are the image pipeline's, bound to video; media_info is video-only.
Later stages (scene detection, keyframes, keyframe pHash, keyframe OCR, duplicate search) are added
step by step per 13-MILESTONE-3-PLAN.md §11.
"""

from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageFailure, StageOutput
from app.pipeline.image_pipeline import HashesStage, MetadataStage
from app.schemas.common import EvidenceClassification, MediaType
from app.services import media_info
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


VIDEO_STAGES: tuple[AnalysisStage, ...] = (
    VideoHashesStage(),
    MediaInfoStage(),
    VideoMetadataStage(),
)
