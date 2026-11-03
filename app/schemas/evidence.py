"""Evidence report returned by GET /artifacts/{id}/evidence.

Every key from 03-API-SPEC.md is kept. Each section also carries `provenance`: the method, tool,
version, timestamps, source, limitations, errors, and review state behind it (04-EVIDENCE-MODEL.md §5).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import JobSummary
from app.schemas.artifact import ArtifactSummary, ReviewInfo
from app.schemas.common import EvidenceClassification, ReviewState, StageStatus
from app.schemas.review import ReviewEventOut

REPORT_NOTICE = (
    "This report lists signals observed in the file and derived from it, with the method and "
    "limitations of each. It does not determine whether the media is authentic, manipulated, or "
    "truthful. Conclusions are for a human analyst to draw."
)


class StageError(BaseModel):
    type: str
    message: str


class DerivedFileInfo(BaseModel):
    derived_file_id: str
    kind: str
    sha256: str
    size_bytes: int


class Provenance(BaseModel):
    evidence_id: str
    stage: str
    status: StageStatus
    classification: EvidenceClassification
    method: str
    source: str
    tool: str
    tool_version: str | None
    started_at: datetime
    completed_at: datetime
    limitations: list[str] = Field(min_length=1)
    errors: list[StageError]
    review_state: ReviewState
    # Why the stage did not run, when status is "skipped".
    skip_reason: str | None = None
    derived_files: list[DerivedFileInfo] = []
    # Record-level review by the analyst (M2-2). Never changes `classification`.
    analyst_notes: str = ""
    review_updated_at: datetime | None = None


class HashesSection(BaseModel):
    sha256: str | None
    md5: str | None
    matches_upload_record: bool | None
    provenance: Provenance


class MetadataSection(BaseModel):
    exif: dict[str, dict[str, Any]]
    xmp: dict[str, dict[str, Any]]
    iptc: dict[str, dict[str, Any]]
    other: dict[str, dict[str, Any]]
    composite: dict[str, dict[str, Any]]
    provenance: Provenance


class C2PASection(BaseModel):
    present: bool | None
    validation_performed: Literal[False] = False
    manifest_labels: list[str]
    details: dict[str, Any]
    provenance: Provenance


class PerceptualHashSection(BaseModel):
    algorithm: Literal["pHash"] = "pHash"
    bits: int
    value: str | None
    provenance: Provenance


class OCRPreprocessingStep(BaseModel):
    step: str
    applied: bool
    description: str
    parameters: dict[str, Any] = {}


class OCRCandidate(BaseModel):
    """One Tesseract pass. Both passes are reported, whichever was selected."""

    variant: Literal["grayscale", "threshold"]
    status: Literal["succeeded", "failed"]
    text: str | None
    confidence: float | None
    word_count: int | None
    error: str | None


class OCRSelection(BaseModel):
    variant: Literal["grayscale", "threshold"]
    reason: str


class OCRCleaningRule(BaseModel):
    rule: str
    description: str
    lines_affected: int


class OCRSection(BaseModel):
    engine: Literal["tesseract"] = "tesseract"
    languages: list[str]
    # Raw Tesseract text of the selected pass, unchanged.
    text: str
    # Text after cosmetic cleaning, or None when cleaning changed nothing (or for older records).
    cleaned_text: str | None = None
    cleaning: list[OCRCleaningRule] = []
    confidence: float | None
    word_count: int
    preprocessing: list[OCRPreprocessingStep] = []
    # Empty, and `selected` None, for records made before two-pass OCR.
    candidates: list[OCRCandidate] = []
    selected: OCRSelection | None = None
    provenance: Provenance


class DuplicateMatch(BaseModel):
    artifact_id: str
    # Current filename, or None if the matched artifact has since been deleted.
    filename: str | None
    available: bool
    similarity: float
    distance: int
    match_type: Literal["exact_file", "visually_identical", "near"]


class DuplicatesSection(BaseModel):
    algorithm: Literal["pHash"] = "pHash"
    threshold: int | None
    library_size: int | None
    compared: int | None
    # Artifacts excluded from duplicate search by the analyst (M2-7). None for records made before M2.
    excluded_count: int | None = None
    matches: list[DuplicateMatch]
    provenance: Provenance


class EvidenceReport(BaseModel):
    # 1.1 (Milestone 2) adds record-level review in `provenance` and `review_history`; nothing removed.
    schema_version: Literal["1.1"] = "1.1"
    artifact_id: str
    job_id: str
    created_at: datetime
    notice: str = REPORT_NOTICE
    artifact: ArtifactSummary
    job: JobSummary
    hashes: HashesSection | None
    metadata: MetadataSection | None
    c2pa: C2PASection | None
    perceptual_hash: PerceptualHashSection | None
    ocr: OCRSection | None
    duplicates: DuplicatesSection | None
    review: ReviewInfo
    # Every review change for this artifact, artifact- and record-level, newest first.
    review_history: list[ReviewEventOut] = []
