"""Forensic indicators and measurements (Pass 2, D25).

Numbers and observable facts that help an analyst judge how a file was produced: JPEG quantisation
tables and the quality they imply, per-channel pixel statistics, whether the dimensions the metadata
declares match the pixels actually decoded, and for video the keyframe spacing and packet-size
distribution.

None of this decides whether media was edited. Re-encoding, resizing, exporting, and ordinary
platform processing all change these numbers, and so does nothing at all. Every value is reported
with the method that produced it; thresholds and verdicts are deliberately absent. In particular
Vestigo does not implement error-level analysis, whose coloured output is routinely read as proof of
editing when it shows nothing of the kind.
"""

import json
import math
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.core.tools import ToolStatus, run_tool

FORENSIC_LIMITATIONS: tuple[str, ...] = (
    "These are measurements, not conclusions. They describe how the file was encoded, which changes "
    "whenever media is re-saved, resized, exported, or passed through a platform - and which also "
    "stays unremarkable in files that were edited heavily.",
    "A quantisation table implies the quality setting of the LAST save only. A high or unusual "
    "quality says nothing about what happened before that save, and nothing about the content.",
    "Pixel statistics describe the image as it decodes now. They are not a measure of authenticity, "
    "and no threshold separating 'edited' from 'original' is applied anywhere in Vestigo.",
    "A mismatch between declared and decoded dimensions is reported as a fact. It is common after "
    "cropping tools, resizers, and metadata editors, and is not evidence of deception.",
    "Vestigo does not implement error-level analysis or any similar visual overlay: its output is "
    "routinely misread as proof of editing, which it is not.",
    "Video keyframe spacing and packet sizes reflect the encoder and its settings. Differences "
    "between files mean they were encoded differently, not that either was altered.",
)

# The IJG standard luminance table, used only to express a measured table as an implied quality.
STANDARD_LUMINANCE = (
    16,
    11,
    10,
    16,
    24,
    40,
    51,
    61,
    12,
    12,
    14,
    19,
    26,
    58,
    60,
    55,
    14,
    13,
    16,
    24,
    40,
    57,
    69,
    56,
    14,
    17,
    22,
    29,
    51,
    87,
    80,
    62,
    18,
    22,
    37,
    56,
    68,
    109,
    103,
    77,
    24,
    35,
    55,
    64,
    81,
    104,
    113,
    92,
    49,
    64,
    78,
    87,
    103,
    121,
    120,
    101,
    72,
    92,
    95,
    98,
    112,
    100,
    103,
    99,
)


@dataclass
class QuantizationTable:
    index: int
    precision: int
    values: list[int]
    # The IJG quality setting whose standard table is closest to this one, where it can be implied.
    implied_quality: int | None = None
    matches_standard: bool = False


@dataclass
class ForensicReport:
    container: str | None = None
    quantization_tables: list[QuantizationTable] = field(default_factory=list)
    # Per-channel statistics of the decoded pixels.
    channel_statistics: list[dict[str, Any]] = field(default_factory=list)
    decoded_width: int | None = None
    decoded_height: int | None = None
    declared_width: int | None = None
    declared_height: int | None = None
    dimensions_match: bool | None = None
    # Video: keyframe spacing and packet-size distribution.
    video_statistics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _implied_quality(values: list[int]) -> tuple[int | None, bool]:
    """The IJG quality whose standard table best matches, by least squared difference."""
    if len(values) < 64:
        return None, False
    best_quality: int | None = None
    best_error = float("inf")
    for quality in range(1, 101):
        scale = 5000 // quality if quality < 50 else 200 - quality * 2
        error = 0.0
        for standard, actual in zip(STANDARD_LUMINANCE, values[:64], strict=False):
            expected = max(1, min(255, (standard * scale + 50) // 100))
            error += (expected - actual) ** 2
        if error < best_error:
            best_error = error
            best_quality = quality
    return best_quality, best_error == 0.0


def jpeg_quantization_tables(data: bytes) -> list[QuantizationTable]:
    """Every DQT table in the file, in order, with the quality each implies."""
    tables: list[QuantizationTable] = []
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        if marker == 0xD9:
            break
        (length,) = struct.unpack(">H", data[offset + 2 : offset + 4])
        if marker == 0xDB:
            cursor = offset + 4
            end = offset + 2 + length
            while cursor < end and cursor < len(data):
                spec = data[cursor]
                precision = spec >> 4
                index = spec & 0x0F
                count = 64 * (2 if precision else 1)
                raw = data[cursor + 1 : cursor + 1 + count]
                if len(raw) < count:
                    break
                if precision:
                    values = [struct.unpack(">H", raw[i : i + 2])[0] for i in range(0, len(raw), 2)]
                else:
                    values = list(raw)
                quality, exact = _implied_quality(values)
                tables.append(
                    QuantizationTable(
                        index=index,
                        precision=8 if precision == 0 else 16,
                        values=values,
                        implied_quality=quality,
                        matches_standard=exact,
                    )
                )
                cursor += 1 + count
        if marker == 0xDA:
            break
        offset += 2 + length
    return tables


def channel_statistics(path: Path) -> tuple[list[dict[str, Any]], int | None, int | None]:
    """Mean, standard deviation, and range per channel of the decoded pixels."""
    try:
        import numpy as np
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
            pixels = np.asarray(image.convert("RGB"), dtype=np.float64)
    except Exception:  # noqa: BLE001 - a file we cannot decode simply has no pixel statistics
        return [], None, None
    if pixels.size == 0:
        return [], width, height
    statistics = []
    for index, name in enumerate(("red", "green", "blue")):
        plane = pixels[:, :, index]
        statistics.append(
            {
                "channel": name,
                "mean": round(float(plane.mean()), 4),
                "standard_deviation": round(float(plane.std()), 4),
                "minimum": int(plane.min()),
                "maximum": int(plane.max()),
            }
        )
    return statistics, width, height


def _series_statistics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {}
    ordered = sorted(values)
    count = len(ordered)
    mean = sum(ordered) / count
    variance = sum((value - mean) ** 2 for value in ordered) / count
    return {
        "count": count,
        "mean": round(mean, 4),
        "standard_deviation": round(math.sqrt(variance), 4),
        "minimum": round(ordered[0], 4),
        "median": round(ordered[count // 2], 4),
        "maximum": round(ordered[-1], 4),
    }


def video_statistics(tool: ToolStatus, path: Path, timeout: float, max_packets: int = 4000) -> dict[str, Any]:
    """Keyframe spacing and packet sizes from ffprobe, as distributions rather than judgements."""
    completed = run_tool(
        tool,
        [
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "packet=pts_time,size,flags",
            "-print_format",
            "json",
            "-read_intervals",
            "%+#" + str(max_packets),
            path,
        ],
        timeout=timeout,
    )
    try:
        packets = json.loads(completed.stdout or b"{}").get("packets") or []
    except json.JSONDecodeError:
        return {"error": "ffprobe returned output that is not valid JSON."}

    sizes: list[float] = []
    keyframe_times: list[float] = []
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        try:
            sizes.append(float(packet.get("size", 0)))
        except (TypeError, ValueError):
            pass
        if "K" in str(packet.get("flags", "")):
            try:
                keyframe_times.append(float(packet.get("pts_time", 0.0)))
            except (TypeError, ValueError):
                pass
    intervals = [
        round(second - first, 4) for first, second in zip(keyframe_times, keyframe_times[1:], strict=False)
    ]
    return {
        "packets_examined": len(packets),
        "keyframe_count": len(keyframe_times),
        "keyframe_interval_seconds": _series_statistics(intervals),
        "packet_size_bytes": _series_statistics(sizes),
    }


def inspect_image(path: Path, declared: tuple[int | None, int | None] = (None, None)) -> ForensicReport:
    """Encoding and pixel measurements for a still image."""
    report = ForensicReport()
    head = path.read_bytes() if path.stat().st_size <= (16 << 20) else path.open("rb").read(16 << 20)
    if head.startswith(b"\xff\xd8\xff"):
        report.container = "jpeg"
        report.quantization_tables = jpeg_quantization_tables(head)
        if not report.quantization_tables:
            report.notes.append("No quantisation tables were found in this JPEG.")
    else:
        report.notes.append("Quantisation tables apply to JPEG only; this container stores no such tables.")

    report.channel_statistics, report.decoded_width, report.decoded_height = channel_statistics(path)
    if not report.channel_statistics:
        report.warnings.append("The pixels could not be decoded, so no pixel statistics were measured.")

    report.declared_width, report.declared_height = declared
    if report.declared_width and report.declared_height and report.decoded_width and report.decoded_height:
        report.dimensions_match = (
            int(report.declared_width) == report.decoded_width
            and int(report.declared_height) == report.decoded_height
        )
        if not report.dimensions_match:
            report.notes.append(
                f"The metadata declares {report.declared_width}x{report.declared_height} while the "
                f"pixels decode to {report.decoded_width}x{report.decoded_height}. Recorded as found."
            )
    return report
