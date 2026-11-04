"""Summarises ffprobe output for the media_info stage (Milestone 3).

Everything here restates what ffprobe read from container and stream headers. Values are reported as
written; nothing is decoded or verified (decisions M3-7, M3-8).
"""

from typing import Any


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def frame_rate(stream: dict) -> float | None:
    """avg_frame_rate like "25/1" as a number, or None when the container does not report one."""
    text = stream.get("avg_frame_rate") or ""
    numerator, _, denominator = text.partition("/")
    top, bottom = _float(numerator), _float(denominator or "1")
    if top is None or not bottom:
        return None
    return round(top / bottom, 3)


def rotation(stream: dict) -> int | None:
    """Display-matrix rotation in degrees, when the stream carries one."""
    for side_data in stream.get("side_data_list") or []:
        value = _int(side_data.get("rotation"))
        if value is not None:
            return value
    return None


def summarize(probe: dict) -> dict[str, Any]:
    """The media_info evidence payload from a parsed ffprobe result."""
    container = probe.get("format", {})
    streams = probe.get("streams", [])
    video_streams, audio_streams, other_streams = [], [], []
    for stream in streams:
        kind = stream.get("codec_type")
        if kind == "video" and not stream.get("disposition", {}).get("attached_pic"):
            video_streams.append(
                {
                    "index": stream.get("index"),
                    "codec": stream.get("codec_name"),
                    "profile": stream.get("profile"),
                    "width": _int(stream.get("width")),
                    "height": _int(stream.get("height")),
                    "frame_rate": frame_rate(stream),
                    "bit_rate": _int(stream.get("bit_rate")),
                    "pixel_format": stream.get("pix_fmt"),
                    "rotation": rotation(stream),
                }
            )
        elif kind == "audio":
            audio_streams.append(
                {
                    "index": stream.get("index"),
                    "codec": stream.get("codec_name"),
                    "profile": stream.get("profile"),
                    "channels": _int(stream.get("channels")),
                    "channel_layout": stream.get("channel_layout"),
                    "sample_rate": _int(stream.get("sample_rate")),
                    "bit_rate": _int(stream.get("bit_rate")),
                }
            )
        else:
            other_streams.append(
                {"index": stream.get("index"), "codec_type": kind, "codec": stream.get("codec_name")}
            )
    return {
        "container": {
            "format_name": container.get("format_name"),
            "format_long_name": container.get("format_long_name"),
            # As written in the container (decision M3-8), not measured by decoding.
            "duration_seconds": _float(container.get("duration")),
            "size_bytes": _int(container.get("size")),
            "bit_rate": _int(container.get("bit_rate")),
            "stream_count": len(streams),
        },
        "video_streams": video_streams,
        "audio_streams": audio_streams,
        "other_streams": other_streams,
    }
