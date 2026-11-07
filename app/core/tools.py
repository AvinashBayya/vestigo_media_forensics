"""External command-line tools: discovery, version detection, and safe invocation.

Versions are probed once and cached, and the same values are used by /health and by every evidence
record, so the two always agree.
"""

import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ToolState = Literal["ok", "missing", "error"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version_args: tuple[str, ...]
    version_pattern: str
    used_in: str
    required: bool
    required_languages: tuple[str, ...] = ()


TOOL_SPECS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec("exiftool", ("-ver",), r"^\s*(\S+)", "M1: metadata, C2PA detection", True),
        # Optional (Pass 2): signature scanning only, never extraction. Absent is fine.
        ToolSpec("binwalk", ("--version",), r"v?(\d[\d.]*)", "Pass 2: signature scan", False),
        ToolSpec("tesseract", ("--version",), r"tesseract\s+v?(\S+)", "M1: OCR", True, ("eng",)),
        ToolSpec("ffmpeg", ("-version",), r"ffmpeg version (\S+)", "M3: keyframes, scene detection", True),
        ToolSpec(
            "ffprobe", ("-version",), r"ffprobe version (\S+)", "M3: video validation, media info", True
        ),
    )
}


@dataclass(frozen=True)
class ToolStatus:
    name: str
    status: ToolState
    version: str | None = None
    path: str | None = None
    detail: str | None = None
    languages: tuple[str, ...] = field(default=())


class ToolError(Exception):
    error_type = "TOOL_ERROR"


class ToolUnavailableError(ToolError):
    error_type = "TOOL_UNAVAILABLE"


class ToolTimeoutError(ToolError):
    error_type = "TOOL_TIMEOUT"


class ToolOutputError(ToolError):
    error_type = "TOOL_OUTPUT_INVALID"


class ToolRegistry:
    def __init__(
        self,
        specs: dict[str, ToolSpec] | None = None,
        ttl_seconds: float = 60.0,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.specs = specs if specs is not None else TOOL_SPECS
        self._ttl = ttl_seconds
        self._which = which
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, ToolStatus]] = {}

    def status(self, name: str) -> ToolStatus:
        with self._lock:
            cached = self._cache.get(name)
            if cached and time.monotonic() - cached[0] < self._ttl:
                return cached[1]
        result = self._probe(self.specs[name])
        with self._lock:
            self._cache[name] = (time.monotonic(), result)
        return result

    def all_statuses(self) -> dict[str, ToolStatus]:
        return {name: self.status(name) for name in self.specs}

    def require(self, name: str) -> ToolStatus:
        status = self.status(name)
        if status.status != "ok":
            raise ToolUnavailableError(f"{name} is not available: {status.detail or status.status}.")
        return status

    def _probe(self, spec: ToolSpec) -> ToolStatus:
        path = self._which(spec.name)
        if path is None:
            return ToolStatus(spec.name, "missing", detail="not found on PATH")
        try:
            output = _run_quick([path, *spec.version_args])
        except (OSError, subprocess.SubprocessError):
            return ToolStatus(spec.name, "error", path=path, detail="version check failed")
        match = re.search(spec.version_pattern, output)
        if match is None:
            return ToolStatus(spec.name, "error", path=path, detail="unrecognised version output")
        version = match.group(1)

        languages: tuple[str, ...] = ()
        if spec.required_languages:
            try:
                lines = _run_quick([path, "--list-langs"]).splitlines()
            except (OSError, subprocess.SubprocessError):
                return ToolStatus(spec.name, "error", version, path, "language list failed")
            languages = tuple(line.strip() for line in lines[1:] if line.strip())
            missing = [lang for lang in spec.required_languages if lang not in languages]
            if missing:
                detail = f"language data missing: {', '.join(missing)}"
                return ToolStatus(spec.name, "error", version, path, detail, languages)
        return ToolStatus(spec.name, "ok", version, path, languages=languages)


def _run_quick(args: Sequence[str]) -> str:
    completed = subprocess.run(
        list(args), capture_output=True, timeout=10, check=True, stdin=subprocess.DEVNULL
    )
    return (completed.stdout or completed.stderr).decode("utf-8", errors="replace")


def run_tool(
    tool: ToolStatus, args: Sequence[str | Path], *, timeout: float, cwd: Path | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Run a tool with an argument list (never a shell) and a timeout."""
    if tool.path is None:
        raise ToolUnavailableError(f"{tool.name} is not available.")
    try:
        return subprocess.run(
            [tool.path, *(str(arg) for arg in args)],
            capture_output=True,
            timeout=timeout,
            check=False,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolTimeoutError(f"{tool.name} did not finish within {timeout:g} seconds.") from exc
    except OSError as exc:
        raise ToolUnavailableError(f"{tool.name} could not be started ({exc.strerror}).") from exc
