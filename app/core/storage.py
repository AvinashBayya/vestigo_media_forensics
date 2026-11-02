"""Local file storage under the data directory.

Layout:
    artifacts/{artifact_id}/original/{artifact_id}.{ext}   uploaded file, read-only
    artifacts/{artifact_id}/derived/{job_id}/...          files produced by analysis
    tmp/                                                  uploads and scratch files in progress
    trash/                                                artifacts being deleted

Every path is built from validated IDs and checked to stay inside the data directory.
User-supplied filenames are never used in paths.
"""

import os
import shutil
import stat
import uuid
from pathlib import Path

from app.core import ids


class UnsafePathError(ValueError):
    pass


def _make_writable_and_retry(func, path, _exc_info) -> None:  # noqa: ANN001 (shutil.rmtree callback)
    os.chmod(path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
    func(path)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, onerror=_make_writable_and_retry)
    else:
        path.unlink(missing_ok=True)


class Storage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.artifacts_dir = self.root / "artifacts"
        self.tmp_dir = self.root / "tmp"
        self.trash_dir = self.root / "trash"

    def prepare(self) -> None:
        """Create the layout and clear leftovers from interrupted uploads or deletions."""
        for directory in (self.artifacts_dir, self.tmp_dir, self.trash_dir):
            directory.mkdir(parents=True, exist_ok=True)
        for directory in (self.tmp_dir, self.trash_dir):
            for child in directory.iterdir():
                _remove(child)

    def resolve(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise UnsafePathError("Path escapes the data directory.")
        return path

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def artifact_dir(self, artifact_id: str) -> Path:
        if not ids.is_valid_id(artifact_id, ids.ARTIFACT):
            raise UnsafePathError("Invalid artifact ID.")
        return self.artifacts_dir / artifact_id

    def derived_dir(self, artifact_id: str, job_id: str) -> Path:
        if not ids.is_valid_id(job_id, ids.JOB):
            raise UnsafePathError("Invalid job ID.")
        return self.artifact_dir(artifact_id) / "derived" / job_id

    def new_temp_path(self, suffix: str = "") -> Path:
        return self.tmp_dir / f"{uuid.uuid4().hex}{suffix}"

    def store_original(self, temp_path: Path, artifact_id: str, extension: str) -> str:
        """Move a validated upload into place, make it read-only, and return its relative path."""
        directory = self.artifact_dir(artifact_id) / "original"
        directory.mkdir(parents=True)
        target = directory / f"{artifact_id}.{extension}"
        os.replace(temp_path, target)
        target.chmod(0o444)
        return self.relative(target)

    def count_files(self, artifact_id: str) -> tuple[int, int]:
        """Return (original files, derived files) currently on disk for an artifact."""
        directory = self.artifact_dir(artifact_id)

        def count(path: Path) -> int:
            return sum(1 for item in path.rglob("*") if item.is_file()) if path.is_dir() else 0

        return count(directory / "original"), count(directory / "derived")

    def move_to_trash(self, artifact_id: str) -> Path | None:
        source = self.artifact_dir(artifact_id)
        if not source.exists():
            return None
        target = self.trash_dir / f"{artifact_id}-{uuid.uuid4().hex}"
        os.replace(source, target)
        return target

    def restore_from_trash(self, trashed: Path, artifact_id: str) -> None:
        os.replace(trashed, self.artifact_dir(artifact_id))

    def purge(self, path: Path) -> None:
        _remove(path)

    def is_healthy(self) -> bool:
        try:
            probe = self.new_temp_path(".probe")
            probe.write_bytes(b"ok")
            readable = probe.read_bytes() == b"ok"
            probe.unlink()
            return readable and self.artifacts_dir.is_dir()
        except OSError:
            return False
