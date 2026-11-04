"""Upload validation: the file type comes from the file's own bytes, never its name or a client header.

Images are verified with Pillow; videos with ffprobe (decision M3-1). Uploads are never executed.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.tools import ToolStatus, run_tool


@dataclass(frozen=True)
class ImageFormat:
    name: str
    mime_type: str
    extension: str
    pillow_format: str


# Pillow's JPEG decoder also handles MPO (multi-picture JPEG from cameras).
JPEG = ImageFormat("jpeg", "image/jpeg", "jpg", "JPEG")
PNG = ImageFormat("png", "image/png", "png", "PNG")
WEBP = ImageFormat("webp", "image/webp", "webp", "WEBP")
TIFF = ImageFormat("tiff", "image/tiff", "tiff", "TIFF")
SNIFF_BYTES = 16


class InvalidImageError(Exception):
    pass


class ImageTooLargeError(Exception):
    pass


@dataclass(frozen=True)
class ImageInfo:
    format: ImageFormat
    width: int
    height: int


def sniff_image_format(head: bytes) -> ImageFormat | None:
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return TIFF
    return None


def inspect_image(path: Path, expected: ImageFormat, max_pixels: int) -> ImageInfo:
    """Confirm the file parses as the sniffed format and is within the pixel limit.

    Only the decoder for the sniffed format is allowed, so Pillow never falls back to another
    format's parser. The header is checked without decoding the full image.
    """
    try:
        with Image.open(path, formats=[expected.pillow_format]) as image:
            width, height = image.size
            if width * height > max_pixels:
                raise ImageTooLargeError(f"{width}x{height}")
            image.verify()
    except Image.DecompressionBombError as exc:
        raise ImageTooLargeError(str(exc)) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as exc:
        raise InvalidImageError(type(exc).__name__) from exc
    return ImageInfo(expected, width, height)


# --- Video (Milestone 3) ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoFormat:
    name: str
    mime_type: str
    extension: str


MP4 = VideoFormat("mp4", "video/mp4", "mp4")
MOV = VideoFormat("mov", "video/quicktime", "mov")
WEBM = VideoFormat("webm", "video/webm", "webm")
MKV = VideoFormat("mkv", "video/x-matroska", "mkv")

# WebM is Matroska restricted to these codecs; anything else in an EBML file is plain Matroska.
WEBM_VIDEO_CODECS = frozenset({"vp8", "vp9", "av1"})
WEBM_AUDIO_CODECS = frozenset({"vorbis", "opus"})


class InvalidVideoError(Exception):
    """The file sniffed as a video container but could not be read as a valid video."""


class VideoTooLongError(Exception):
    def __init__(self, duration_seconds: float) -> None:
        super().__init__(f"{duration_seconds:g} s")
        self.duration_seconds = duration_seconds


class VideoResolutionError(Exception):
    def __init__(self, width: int, height: int) -> None:
        super().__init__(f"{width}x{height}")
        self.width = width
        self.height = height


@dataclass(frozen=True)
class VideoInfo:
    format: VideoFormat
    width: int
    height: int
    # As reported by the container (decision M3-8); not a decode-verified measurement.
    duration_seconds: float


def sniff_video_container(head: bytes) -> str | None:
    """ "iso_media" (MP4/MOV family), "matroska" (WebM/MKV family), or None."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "iso_media"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "matroska"
    return None


def _resolve_format(container: str, head: bytes, streams: list[dict]) -> VideoFormat:
    if container == "iso_media":
        return MOV if head[8:12] == b"qt  " else MP4
    codecs_fit_webm = all(
        (s.get("codec_type") == "video" and s.get("codec_name") in WEBM_VIDEO_CODECS)
        or (s.get("codec_type") == "audio" and s.get("codec_name") in WEBM_AUDIO_CODECS)
        for s in streams
    )
    return WEBM if streams and codecs_fit_webm else MKV


def _duration_seconds(probe: dict) -> float | None:
    candidates = [probe.get("format", {}).get("duration")]
    candidates += [stream.get("duration") for stream in probe.get("streams", [])]
    values = []
    for candidate in candidates:
        try:
            values.append(float(candidate))
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def probe_video(ffprobe: ToolStatus, path: Path, timeout: float) -> dict:
    """ffprobe's JSON description of the file. Raises InvalidVideoError if it cannot be read."""
    args = ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    completed = run_tool(ffprobe, args, timeout=timeout)
    if completed.returncode != 0:
        raise InvalidVideoError("ffprobe could not read the file")
    try:
        probe = json.loads(completed.stdout)
    except ValueError as exc:
        raise InvalidVideoError("ffprobe produced unreadable output") from exc
    if not isinstance(probe, dict) or not probe.get("streams"):
        raise InvalidVideoError("the file contains no streams")
    return probe


def inspect_video(
    ffprobe: ToolStatus,
    path: Path,
    container: str,
    head: bytes,
    *,
    max_pixels: int,
    max_duration_seconds: float,
    timeout: float,
) -> VideoInfo:
    """Confirm the sniffed container holds a decodable video within the limits (M3-2)."""
    probe = probe_video(ffprobe, path, timeout)
    streams = probe["streams"]
    video_streams = [
        s
        for s in streams
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
    ]
    if not video_streams:
        raise InvalidVideoError("the file contains no video stream")
    first = video_streams[0]
    width, height = int(first.get("width") or 0), int(first.get("height") or 0)
    if width <= 0 or height <= 0:
        raise InvalidVideoError("the video stream has no readable dimensions")
    if width * height > max_pixels:
        raise VideoResolutionError(width, height)
    duration = _duration_seconds(probe)
    if duration is None or duration <= 0:
        raise InvalidVideoError("the container reports no readable duration")
    if duration > max_duration_seconds:
        raise VideoTooLongError(duration)
    return VideoInfo(_resolve_format(container, head, streams), width, height, round(duration, 3))
