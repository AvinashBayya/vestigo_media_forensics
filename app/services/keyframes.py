"""Keyframe selection and extraction (Milestone 3, plan §8).

Selection is deterministic and bounded, and every choice is recorded:

1. The first decodable frame is always selected.
2. One frame per scene change (when scene detection ran and found any).
3. Fewer than MIN_KEYFRAMES selected → evenly spaced frames fill up to the minimum.
4. More than the configured cap → the first frame plus the highest-scoring scene changes are kept.

Frames are extracted with ffmpeg one at a time (fast seek, one decoded frame, display-matrix
autorotation) as JPEG thumbnails capped at THUMBNAIL_MAX_SIDE pixels on the longest side.
"""

from dataclasses import dataclass
from pathlib import Path

from app.core.tools import ToolStatus, run_tool
from app.services.scenes import SceneChange

MIN_KEYFRAMES = 8
# Candidates closer than this to an already-selected frame are dropped.
DEDUPE_SECONDS = 0.25
# Nothing decodable sits at the container-reported end; stay a little before it.
END_MARGIN_SECONDS = 0.2
THUMBNAIL_MAX_SIDE = 1920
JPEG_QUALITY = "2"
# Keyframe OCR analyses at most this many frames (decision M3-3).
OCR_KEYFRAME_LIMIT = 10


@dataclass(frozen=True)
class SelectedKeyframe:
    seq: int
    timestamp: float
    reason: str  # "first_frame" | "scene_change" | "uniform_sample"
    scene_score: float | None = None


def _accept(
    selected: list[tuple[float, str, float | None]], candidate: tuple[float, str, float | None]
) -> bool:
    return all(abs(candidate[0] - existing[0]) >= DEDUPE_SECONDS for existing in selected)


def select_keyframes(
    duration_seconds: float, scene_changes: list[SceneChange], max_keyframes: int
) -> list[SelectedKeyframe]:
    """The policy from 13-MILESTONE-3-PLAN.md §8. Returns frames ordered by timestamp, seq 1-based."""
    latest = max(0.0, duration_seconds - END_MARGIN_SECONDS)
    picked: list[tuple[float, str, float | None]] = [(0.0, "first_frame", None)]

    for change in sorted(scene_changes, key=lambda c: -c.score)[: max(0, max_keyframes - 1)]:
        candidate = (min(change.time, latest), "scene_change", change.score)
        if _accept(picked, candidate):
            picked.append(candidate)

    target = min(MIN_KEYFRAMES, max_keyframes)
    if len(picked) < target:
        step = latest / target if target else 0.0
        for index in range(1, target):
            candidate = (round(index * step, 3), "uniform_sample", None)
            if len(picked) >= target:
                break
            if step and _accept(picked, candidate):
                picked.append(candidate)

    picked.sort(key=lambda item: item[0])
    return [
        SelectedKeyframe(seq, round(timestamp, 3), reason, score)
        for seq, (timestamp, reason, score) in enumerate(picked, start=1)
    ]


def extract_keyframe(ffmpeg: ToolStatus, video: Path, timestamp: float, target: Path, timeout: float) -> bool:
    """One frame at `timestamp` as a capped JPEG. ffmpeg applies display-matrix rotation itself.

    Returns False when ffmpeg produced nothing (for example a timestamp past the last frame).
    """
    args = [
        "-v",
        "error",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        video,
        "-frames:v",
        "1",
        "-vf",
        f"scale='min({THUMBNAIL_MAX_SIDE},iw)':-2",
        "-q:v",
        JPEG_QUALITY,
        target,
    ]
    completed = run_tool(ffmpeg, args, timeout=timeout)
    return completed.returncode == 0 and target.is_file() and target.stat().st_size > 0


def evenly_spaced_subset(count: int, limit: int) -> list[int]:
    """Indices of up to `limit` items spread evenly over `count`, always including the first and last."""
    if count <= limit:
        return list(range(count))
    last = count - 1
    return sorted({round(position * last / (limit - 1)) for position in range(limit)})
