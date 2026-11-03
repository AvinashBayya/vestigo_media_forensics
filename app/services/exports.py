"""ZIP evidence package (decision M2-6).

Contents:

- `report.json`: the evidence report for one analysis job, as returned by the API.
- `review.json`: the artifact review, the review of each evidence record in the job, and the full
  review history.
- `derived/…`: raw tool outputs and other files derived during that job.
- `original/…`: the original upload, only when explicitly requested.
- `manifest.json`: SHA-256 and size of every other file, with export details.
- `SHA256SUMS`: the same hashes in `sha256sum -c` format.
- `README.txt`: the evidence notice and how to verify the package.

The package is written to tmp/, streamed, and then removed. Only files recorded for this artifact and
job, inside the artifact's own folder, are read. A recorded derived file that is missing or whose
contents no longer match the recorded SHA-256 is listed in the manifest, never silently dropped.
"""

import hashlib
import json
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app import __version__
from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.models import DerivedFile, EvidenceRecord
from app.schemas.common import ErrorCode
from app.schemas.evidence import REPORT_NOTICE
from app.services import reports, review
from app.services.artifacts import get_artifact, to_review_info

logger = get_logger("exports")

PACKAGE_FORMAT = "vestigo-evidence-package"
PACKAGE_FORMAT_VERSION = "1"
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class ExportPackage:
    path: Path
    filename: str
    sha256: str
    size_bytes: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode("utf-8")


def _readme(artifact_id: str, job_id: str, include_original: bool) -> str:
    return f"""Vestigo evidence package
========================

Artifact: {artifact_id}
Analysis job: {job_id}
Original file included: {"yes" if include_original else "no"}

{REPORT_NOTICE}

Contents
--------
report.json     The evidence report: every check with its method, tool, version, timestamps,
                source, limitations, errors, and review state.
review.json     The analyst's artifact review, the review of each evidence record, and the full
                review history (append-only, with complete note text).
derived/        Raw tool outputs and other files derived during this analysis.
original/       The original upload (only if it was chosen when exporting).
manifest.json   SHA-256 and size of every file above, and export details. Recorded files that were
                missing or did not match their recorded SHA-256 are listed under "problems".
SHA256SUMS      The same hashes, for sha256sum.

Verifying the package
---------------------
1. The SHA-256 of the whole ZIP was sent with the download in the X-Vestigo-Export-SHA256 header,
   and Vestigo shows it after the download. Compare it with:   sha256sum <this zip file>
2. After unzipping, check every file against the manifest:
      sha256sum -c SHA256SUMS
   On macOS:  shasum -a 256 -c SHA256SUMS
3. Each derived file also lists the SHA-256 recorded when it was created ("recorded_sha256").
"""


def build_export(
    services: AppServices, artifact_id: str, job_id: str | None, include_original: bool
) -> ExportPackage:
    report = reports.build_report(services.db, artifact_id, job_id)
    artifact = get_artifact(services.db, artifact_id)
    storage = services.storage
    artifact_dir = storage.artifact_dir(artifact_id).resolve()

    with services.db.reader() as session:
        derived = list(
            session.scalars(
                select(DerivedFile)
                .where(DerivedFile.job_id == report.job_id)
                .order_by(DerivedFile.stored_path)
            )
        )
        records = list(
            session.scalars(
                select(EvidenceRecord)
                .where(EvidenceRecord.job_id == report.job_id)
                .order_by(EvidenceRecord.started_at)
            )
        )
        history = review.history(session, artifact_id)

    review_data = {
        "artifact_id": artifact_id,
        "job_id": report.job_id,
        "artifact_review": to_review_info(artifact).model_dump(mode="json"),
        "record_reviews": [
            {
                "evidence_id": record.id,
                "stage": record.stage,
                "classification": record.classification,
                "review_state": record.review_state,
                "analyst_notes": record.analyst_notes,
                "review_updated_at": record.review_updated_at.isoformat()
                if record.review_updated_at
                else None,
            }
            for record in records
        ],
        "review_history": [event.model_dump(mode="json") for event in history],
    }

    files: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    package_path = storage.new_temp_path(".zip")
    try:
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:

            def add_bytes(name: str, data: bytes, description: str) -> None:
                package.writestr(name, data)
                files.append(
                    {
                        "path": name,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size_bytes": len(data),
                        "description": description,
                    }
                )

            add_bytes("report.json", _json_bytes(report.model_dump(mode="json")), "Evidence report")
            add_bytes("review.json", _json_bytes(review_data), "Analyst review and review history")

            for item in derived:
                name = f"derived/{Path(item.stored_path).name}"
                path = storage.resolve(item.stored_path)
                if not path.resolve().is_relative_to(artifact_dir) or not path.is_file():
                    problems.append(
                        {
                            "path": name,
                            "problem": "missing",
                            "recorded_sha256": item.sha256,
                            "stage": item.stage,
                        }
                    )
                    continue
                actual = _sha256_file(path)
                package.write(path, name)
                files.append(
                    {
                        "path": name,
                        "sha256": actual,
                        "size_bytes": path.stat().st_size,
                        "description": f"Derived file ({item.kind}) from the {item.stage} stage",
                        "stage": item.stage,
                        "kind": item.kind,
                        "recorded_sha256": item.sha256,
                        "matches_record": actual == item.sha256,
                    }
                )
                if actual != item.sha256:
                    problems.append(
                        {
                            "path": name,
                            "problem": "sha256_mismatch",
                            "recorded_sha256": item.sha256,
                            "stage": item.stage,
                        }
                    )

            if include_original:
                path = storage.resolve(artifact.stored_path)
                name = f"original/{path.name}"
                actual = _sha256_file(path)
                package.write(path, name)
                files.append(
                    {
                        "path": name,
                        "sha256": actual,
                        "size_bytes": path.stat().st_size,
                        "description": "Original upload",
                        "original_filename": artifact.original_filename,
                        "recorded_sha256": artifact.sha256,
                        "matches_record": actual == artifact.sha256,
                    }
                )
                if actual != artifact.sha256:
                    problems.append(
                        {"path": name, "problem": "sha256_mismatch", "recorded_sha256": artifact.sha256}
                    )

            readme = _readme(artifact_id, report.job_id, include_original).encode("utf-8")
            add_bytes("README.txt", readme, "How to read and verify this package")
            manifest = {
                "format": PACKAGE_FORMAT,
                "format_version": PACKAGE_FORMAT_VERSION,
                "generator": f"Vestigo Media Forensics {__version__}",
                "exported_at": utcnow().isoformat(),
                "artifact_id": artifact_id,
                "job_id": report.job_id,
                "report_schema_version": report.schema_version,
                "original_filename": artifact.original_filename,
                "original_included": include_original,
                "notice": REPORT_NOTICE,
                "files": files,
                "problems": problems,
            }
            package.writestr("manifest.json", _json_bytes(manifest))
            sums = "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in files)
            package.writestr("SHA256SUMS", sums)
    except OSError as exc:
        package_path.unlink(missing_ok=True)
        log_event(
            logger, logging.ERROR, "export.failed", artifact_id=artifact_id, error_type=type(exc).__name__
        )
        raise AppError(
            500, ErrorCode.EXPORT_FAILED, "The evidence package could not be written. No package was created."
        ) from exc
    except BaseException:
        package_path.unlink(missing_ok=True)
        raise

    log_event(
        logger,
        logging.INFO,
        "export.created",
        artifact_id=artifact_id,
        job_id=report.job_id,
        count=len(files),
        status="with_problems" if problems else "ok",
    )
    return ExportPackage(
        path=package_path,
        filename=f"vestigo-evidence-{artifact_id}-{report.job_id}.zip",
        sha256=_sha256_file(package_path),
        size_bytes=package_path.stat().st_size,
    )
