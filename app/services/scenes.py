"""Scene-change detection with ffmpeg's scene filter (Milestone 3).

The filter compares each frame with the previous one and scores how different they are (0–1). Frames
scoring above the threshold are reported with their presentation timestamps. The raw filter output is
kept as a derived file so the parsing can be audited.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.tools import ToolError, ToolStatus, run_tool

_PTS_TIME = re.compile(r"pts_time:(\d+(?:\.\d+)?)")
_SCORE = re.compile(r"lavfi\.scene_score=(\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class SceneChange:
    # Presentation time of the first frame of the new scene, in seconds.
    time: float
    # ffmpeg's scene-change score for that frame (0–1).
    score: float


@dataclass(frozen=True)
class SceneResult:
    changes: list[SceneChange]
    raw_output: bytes


def parse_scene_output(text: str) -> list[SceneChange]:
    """Pairs each frame's pts_time with the lavfi.scene_score printed after it."""
    changes: list[SceneChange] = []
    pending_time: float | None = None
    for line in text.splitlines():
        time_match = _PTS_TIME.search(line)
        if time_match:
            pending_time = float(time_match.group(1))
            continue
        score_match = _SCORE.search(line)
        if score_match and pending_time is not None:
            changes.append(SceneChange(round(pending_time, 3), round(float(score_match.group(1)), 4)))
            pending_time = None
    return changes


def detect_scene_changes(
    ffmpeg: ToolStatus, path: Path, threshold: float, scratch_dir: Path, timeout: float
) -> SceneResult:
    """Run the scene filter over the whole video. Raises ToolError if ffmpeg fails."""
    output = scratch_dir / "scene-changes.txt"
    args = [
        "-v",
        "error",
        "-i",
        path,
        "-vf",
        f"select='gt(scene,{threshold:g})',metadata=print:file={output}",
        "-f",
        "null",
        "-",
    ]
    completed = run_tool(ffmpeg, args, timeout=timeout)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        detail = stderr[-1] if stderr else "no error output"
        raise ToolError(f"ffmpeg exited with code {completed.returncode} ({detail}).")
    raw = output.read_bytes() if output.is_file() else b""
    return SceneResult(parse_scene_output(raw.decode("utf-8", errors="replace")), raw)
