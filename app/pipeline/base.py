"""Pipeline stage interface (02-ARCHITECTURE.md §4).

A stage implements `tool_version()` and `analyze()`. `AnalysisStage.run()` wraps them so that every
result records its timestamps, tool and version, source, limitations, and errors, and so that a
failing stage produces a FAILED result instead of stopping the pipeline.
"""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, final

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.core.config import Settings
from app.core.storage import Storage
from app.core.tools import ToolError, ToolRegistry
from app.models import EvidenceRecord
from app.schemas.analysis import AnalysisOptions, VideoAnalysisOptions
from app.schemas.common import EvidenceClassification, MediaType, StageStatus
from app.schemas.evidence import DerivedFileInfo, StageError
from app.services.duplicates import LibraryReader


@dataclass(frozen=True)
class ArtifactView:
    """Read-only facts about the artifact under analysis."""

    id: str
    path: Path
    media_type: str
    mime_type: str
    sha256: str
    md5: str
    size_bytes: int


class StageFailure(Exception):
    """Raised by a stage that cannot produce a trustworthy result. `data` is kept as evidence."""

    def __init__(self, error_type: str, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.data = data or {}


@dataclass
class StageOutput:
    data: dict[str, Any]
    warnings: list[StageError] = field(default_factory=list)
    extra_limitations: list[str] = field(default_factory=list)


class StageResult(BaseModel):
    stage: str
    status: StageStatus
    classification: EvidenceClassification
    method: str
    source: str
    tool: str
    tool_version: str | None
    started_at: datetime
    completed_at: datetime
    output: dict[str, Any]
    errors: list[StageError]
    limitations: list[str] = Field(min_length=1)
    derived_files: list[DerivedFileInfo] = []

    @property
    def has_output(self) -> bool:
        return self.status in (StageStatus.SUCCEEDED, StageStatus.PARTIAL)


@dataclass(frozen=True)
class PendingDerivedFile:
    info: DerivedFileInfo
    stored_path: str


class DerivedFileWriter:
    """Writes files produced by a stage under derived/{job_id}/ and tracks them for the database."""

    def __init__(self, storage: Storage, artifact_id: str, job_id: str) -> None:
        self._storage = storage
        self._directory = storage.derived_dir(artifact_id, job_id)
        self._pending: dict[str, list[PendingDerivedFile]] = {}

    def write(self, stage: str, kind: str, suffix: str, data: bytes) -> DerivedFileInfo:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{stage}.{suffix}"
        path.write_bytes(data)
        info = DerivedFileInfo(
            derived_file_id=ids.new_id(ids.DERIVED_FILE),
            kind=kind,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )
        self._pending.setdefault(stage, []).append(PendingDerivedFile(info, self._storage.relative(path)))
        return info

    def written(self, stage: str) -> list[DerivedFileInfo]:
        return [pending.info for pending in self._pending.get(stage, [])]

    def take(self, stage: str) -> list[PendingDerivedFile]:
        return self._pending.pop(stage, [])


@dataclass
class StageContext:
    job_id: str
    options: AnalysisOptions | VideoAnalysisOptions
    settings: Settings
    tools: ToolRegistry
    derived: DerivedFileWriter
    library: LibraryReader
    scratch_dir: Path
    results: dict[str, StageResult] = field(default_factory=dict)


class AnalysisStage(ABC):
    name: ClassVar[str]
    media_type: ClassVar[MediaType]
    method: ClassVar[str]
    classification: ClassVar[EvidenceClassification]
    source: ClassVar[str]
    tool_name: ClassVar[str]
    limitations: ClassVar[tuple[str, ...]] = ()
    depends_on: ClassVar[tuple[str, ...]] = ()
    # Name of the AnalysisOptions flag that can switch this stage off, if any.
    option: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "name" in cls.__dict__ and not cls.limitations:
            raise TypeError(f"Stage {cls.__name__} must declare at least one limitation.")

    @abstractmethod
    def tool_version(self, ctx: StageContext) -> str:
        """Version of the tool this stage uses. Raises ToolUnavailableError if it is missing."""

    @abstractmethod
    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput: ...

    def on_recorded(self, record: EvidenceRecord, session: Session) -> None:  # noqa: B027
        """Called in the transaction that saves this stage's evidence record."""

    def skip_reason(self, ctx: StageContext) -> str | None:
        if self.option is not None and not getattr(ctx.options, self.option):
            return f"Disabled by the analysis option '{self.option}'."
        for dependency in self.depends_on:
            previous = ctx.results.get(dependency)
            if previous is None or not previous.has_output:
                return f"Not run because the '{dependency}' stage did not produce a result."
        return None

    @final
    def run(self, artifact: ArtifactView, ctx: StageContext) -> StageResult:
        started_at = utcnow()
        reason = self.skip_reason(ctx)
        if reason is not None:
            return self._result(StageStatus.SKIPPED, started_at, None, {"skip_reason": reason}, [], [], ctx)

        version: str | None = None
        try:
            version = self.tool_version(ctx)
            output = self.analyze(artifact, ctx)
        except ToolError as exc:
            errors = [StageError(type=exc.error_type, message=str(exc))]
            return self._result(StageStatus.FAILED, started_at, version, {}, errors, [], ctx)
        except StageFailure as exc:
            errors = [StageError(type=exc.error_type, message=exc.message)]
            return self._result(StageStatus.FAILED, started_at, version, exc.data, errors, [], ctx)
        except Exception as exc:  # noqa: BLE001 - every failure must be recorded, not raised
            errors = [StageError(type="INTERNAL_ERROR", message=f"{type(exc).__name__}: {exc}")]
            return self._result(StageStatus.FAILED, started_at, version, {}, errors, [], ctx)

        status = StageStatus.PARTIAL if output.warnings else StageStatus.SUCCEEDED
        return self._result(
            status, started_at, version, output.data, output.warnings, output.extra_limitations, ctx
        )

    def _result(
        self,
        status: StageStatus,
        started_at: datetime,
        version: str | None,
        output: dict[str, Any],
        errors: list[StageError],
        extra_limitations: list[str],
        ctx: StageContext,
    ) -> StageResult:
        return StageResult(
            stage=self.name,
            status=status,
            classification=self.classification,
            method=self.method,
            source=self.source,
            tool=self.tool_name,
            tool_version=version,
            started_at=started_at,
            completed_at=utcnow(),
            output=output,
            errors=errors,
            limitations=[*self.limitations, *extra_limitations],
            derived_files=ctx.derived.written(self.name),
        )
