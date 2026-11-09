"""Managed local AI model files (D27).

Model files are staged, never fetched: Vestigo makes no outbound request, so an analyst either drops
a `.cact` archive into `data/models/` or imports one through this service. Both reach the same place,
and the directory scan is the contract, so copying a file in by hand works exactly as well as the
endpoint.

A model file is not evidence. It lives beside the evidence store rather than in it, it is never
hashed into an export manifest, and deleting one removes nothing an analyst recorded.
"""

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile

from app.core.container import AppServices
from app.core.errors import AppError
from app.schemas.common import ErrorCode
from app.services import ai, app_settings

# A staged file is named by the analyst, so the name is constrained rather than trusted: no path
# separators, no leading dot, and nothing that could travel outside the models directory.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

READ_CHUNK = 1024 * 1024

MODEL_LIMITATIONS: tuple[str, ...] = (
    "A model file is a third-party artifact. Vestigo records its name, size, and SHA-256 so a draft "
    "can name the exact bytes that produced it; it does not validate the contents or vouch for them.",
    "Nothing here is downloaded. Staging a model is a deliberate step you take, and the backend "
    "makes no outbound request at any point.",
    "Whether a model can actually run depends on an engine for its generation being present. A file "
    "can be staged and still be unusable, and the status endpoint says which.",
)

NOTICE = (
    "Model files you have staged on this machine. Vestigo never downloads one; drop a .cact file in "
    "the models directory or import it here, and it appears in this list."
)


@dataclass(frozen=True)
class ManagedModel:
    """One staged model file, as measured on disk."""

    name: str
    size_bytes: int
    sha256: str
    modified_at: datetime
    path: str
    # Which settings field currently points at this file, if any.
    configured_for: list[str]


def _models_dir(services: AppServices) -> Path:
    directory = services.storage.models_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _configured_for(services: AppServices, path: Path) -> list[str]:
    editable = app_settings.get_settings_response(services).editable
    fields = {
        "ai_model_path": getattr(editable, "ai_model_path", "") or "",
        "transcription_model_path": getattr(editable, "transcription_model_path", "") or "",
    }
    used: list[str] = []
    for field, raw in fields.items():
        if not raw:
            continue
        try:
            if Path(raw).expanduser().resolve() == path.resolve():
                used.append(field)
        except OSError:  # pragma: no cover - an unresolvable path simply does not match
            continue
    return used


def _describe(services: AppServices, path: Path) -> ManagedModel:
    stat = path.stat()
    return ManagedModel(
        name=path.name,
        size_bytes=stat.st_size,
        sha256=ai.file_digest(path),
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        path=str(path),
        configured_for=_configured_for(services, path),
    )


def list_models(services: AppServices) -> list[ManagedModel]:
    """Every staged model file, newest first. Scans the directory; reads nothing else."""
    directory = _models_dir(services)
    files = [child for child in directory.iterdir() if child.is_file() and child.suffix == ai.MODEL_SUFFIX]
    described = [_describe(services, child) for child in files]
    return sorted(described, key=lambda model: model.modified_at, reverse=True)


def _validate_name(filename: str | None) -> str:
    name = filename or ""
    if not name:
        raise AppError(422, ErrorCode.VALIDATION_ERROR, "The upload has no filename.", {})
    if Path(name).name != name:
        # Stripping the directory part would quietly rename the analyst's file. Say no instead.
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Import the model by its own filename, with no directory part.",
            {"filename": name},
        )
    if Path(name).suffix != ai.MODEL_SUFFIX:
        raise AppError(
            415,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            f"A model file must end in {ai.MODEL_SUFFIX}.",
            {"filename": name},
        )
    if not SAFE_NAME.match(name):
        raise AppError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "A model filename may use letters, digits, dot, dash, and underscore only.",
            {"filename": name},
        )
    return name


def import_model(services: AppServices, upload: UploadFile) -> ManagedModel:
    """Copy an uploaded model file into the managed directory. No network, no overwrite."""
    name = _validate_name(upload.filename)
    directory = _models_dir(services)
    destination = directory / name
    if destination.exists():
        raise AppError(
            409,
            ErrorCode.VALIDATION_ERROR,
            f"A model named {name} is already staged. Delete it first to replace it.",
            {"filename": name},
        )

    limit = services.settings.max_model_bytes
    temporary = services.storage.new_temp_path(".cact")
    written = 0
    try:
        with temporary.open("wb") as handle:
            while chunk := upload.file.read(READ_CHUNK):
                written += len(chunk)
                if written > limit:
                    raise AppError(
                        413,
                        ErrorCode.FILE_TOO_LARGE,
                        f"A model file may be at most {limit} bytes.",
                        {"filename": name, "limit_bytes": limit},
                    )
                handle.write(chunk)
        if written == 0:
            raise AppError(422, ErrorCode.EMPTY_FILE, "The model file is empty.", {"filename": name})
        shutil.move(str(temporary), str(destination))
    finally:
        temporary.unlink(missing_ok=True)
    return _describe(services, destination)


def delete_model(services: AppServices, name: str) -> None:
    """Remove a staged model file, unless a setting still points at it."""
    safe = Path(name).name
    if safe != name or not SAFE_NAME.match(safe) or Path(safe).suffix != ai.MODEL_SUFFIX:
        raise AppError(422, ErrorCode.VALIDATION_ERROR, "That is not a staged model name.", {"name": name})
    path = _models_dir(services) / safe
    if not path.is_file():
        raise AppError(404, ErrorCode.NOT_FOUND, f"No model named {safe} is staged.", {"name": safe})
    used = _configured_for(services, path)
    if used:
        raise AppError(
            409,
            ErrorCode.VALIDATION_ERROR,
            f"{safe} is still selected in Settings ({', '.join(used)}). Change that first.",
            {"name": safe, "configured_for": used},
        )
    path.unlink()
