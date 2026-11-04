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
# Enough for every signature below, including the three MPEG-TS sync bytes at 0/188/376.
SNIFF_BYTES = 512


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
# Additional containers (D19).
AVI = VideoFormat("avi", "video/x-msvideo", "avi")
WMV = VideoFormat("wmv", "video/x-ms-wmv", "wmv")
FLV = VideoFormat("flv", "video/x-flv", "flv")
MPEG_TS = VideoFormat("mpegts", "video/mp2t", "ts")
THREE_GP = VideoFormat("3gp", "video/3gpp", "3gp")
M4V = VideoFormat("m4v", "video/x-m4v", "m4v")

# ASF (WMV/WMA) header object GUID.
_ASF_GUID = bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c")

# Audio formats (D19). The same container machinery validates them; only header-level facts are
# ever read from audio (M3-7).
WAV = VideoFormat("wav", "audio/wav", "wav")
MP3 = VideoFormat("mp3", "audio/mpeg", "mp3")
FLAC = VideoFormat("flac", "audio/flac", "flac")
OGG_AUDIO = VideoFormat("ogg", "audio/ogg", "ogg")
OGG_VIDEO = VideoFormat("ogv", "video/ogg", "ogv")
M4A = VideoFormat("m4a", "audio/mp4", "m4a")

# Families that may resolve to an audio artifact when ffprobe finds no real video stream.
AUDIO_CAPABLE_FAMILIES = frozenset({"wav", "mp3", "flac", "ogg", "iso_media"})

# WebM is Matroska restricted to these codecs; anything else in an EBML file is plain Matroska.
WEBM_VIDEO_CODECS = frozenset({"vp8", "vp9", "av1"})
WEBM_AUDIO_CODECS = frozenset({"vorbis", "opus"})


class InvalidVideoError(Exception):
    """The file sniffed as a video container but could not be read as a valid video."""


class NoVideoStreamError(InvalidVideoError):
    """The container parsed but holds no real video stream (it may still be a valid audio file)."""


class InvalidAudioError(Exception):
    """The file sniffed as an audio container but could not be read as valid audio."""


class AudioTooLongError(Exception):
    def __init__(self, duration_seconds: float) -> None:
        super().__init__(f"{duration_seconds:g} s")
        self.duration_seconds = duration_seconds


@dataclass(frozen=True)
class AudioInfo:
    format: VideoFormat
    # As reported by the container (decision M3-8); not a decode-verified measurement.
    duration_seconds: float


def inspect_audio(probe: dict, container: str, *, max_duration_seconds: float) -> AudioInfo:
    """Confirm an already-probed, video-less container holds audio within the limits (D19)."""
    streams = probe.get("streams", [])
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise InvalidAudioError("the file contains no audio stream")
    duration = _duration_seconds(probe)
    if duration is None or duration <= 0:
        raise InvalidAudioError("the container reports no readable duration")
    if duration > max_duration_seconds:
        raise AudioTooLongError(duration)
    return AudioInfo(resolve_audio_format(container), round(duration, 3))


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
    """The container family from the file's bytes, or None.

    "iso_media" (MP4/MOV/3GP/M4V family) and "matroska" (WebM/MKV) are resolved further after
    ffprobe; the others map straight to one format. The weak MPEG-TS signature (0x47 sync bytes at
    packet boundaries) is checked last.
    """
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "iso_media"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "matroska"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    if head.startswith(_ASF_GUID):
        return "asf"
    if head.startswith(b"FLV\x01"):
        return "flv"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"fLaC"):
        return "flac"
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "mp3"
    if len(head) >= 377 and head[0] == 0x47 and head[188] == 0x47 and head[376] == 0x47:
        return "mpeg_ts"
    return None


def has_real_video_stream(streams: list[dict]) -> bool:
    """A video stream that is not attached cover art (album covers in MP3/M4A do not count)."""
    return any(
        s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic") for s in streams
    )


def resolve_audio_format(container: str) -> VideoFormat:
    return {"wav": WAV, "mp3": MP3, "flac": FLAC, "ogg": OGG_AUDIO, "iso_media": M4A}[container]


def _resolve_format(container: str, head: bytes, streams: list[dict]) -> VideoFormat:
    direct = {"avi": AVI, "asf": WMV, "flv": FLV, "mpeg_ts": MPEG_TS, "ogg": OGG_VIDEO}
    if container in direct:
        return direct[container]
    if container == "iso_media":
        brand = head[8:12]
        if brand == b"qt  ":
            return MOV
        if brand[:3] in (b"3gp", b"3g2"):
            return THREE_GP
        if brand == b"M4V ":
            return M4V
        return MP4
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


@dataclass(frozen=True)
class ProbeResult:
    data: dict
    raw_output: bytes


def probe_video(ffprobe: ToolStatus, path: Path, timeout: float) -> ProbeResult:
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
    return ProbeResult(probe, completed.stdout)


def inspect_video(
    probe: dict,
    container: str,
    head: bytes,
    *,
    max_pixels: int,
    max_duration_seconds: float,
) -> VideoInfo:
    """Confirm an already-probed container holds a video within the limits (M3-2)."""
    streams = probe["streams"]
    video_streams = [
        s
        for s in streams
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
    ]
    if not video_streams:
        raise NoVideoStreamError("the file contains no video stream")
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
