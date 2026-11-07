"""Evidence report returned by GET /artifacts/{id}/evidence.

Every key from 03-API-SPEC.md is kept. Each section also carries `provenance`: the method, tool,
version, timestamps, source, limitations, errors, and review state behind it (04-EVIDENCE-MODEL.md §5).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import JobSummary
from app.schemas.artifact import ArtifactSummary, ReviewInfo
from app.schemas.common import EvidenceClassification, MediaType, ReviewState, StageStatus
from app.schemas.leads import ExternalLeadInfo
from app.schemas.location_candidates import LocationCandidateInfo
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


class C2PAManifestInfo(BaseModel):
    """One manifest in the store (M4): who claims to have produced it and how it was signed."""

    label: str
    title: str | None = None
    claim_generator: str | None = None
    signature_issuer: str | None = None
    signature_common_name: str | None = None
    signature_cert_serial: str | None = None
    signature_time: str | None = None
    signature_algorithm: str | None = None
    assertion_labels: list[str] = []
    ingredient_count: int = 0


class C2PASection(BaseModel):
    present: bool | None
    # False on records made before Milestone 4 (detection only); True since local validation (D20).
    validation_performed: bool = False
    manifest_labels: list[str]
    details: dict[str, Any]
    # Vestigo's summary of the validator outcome: valid, invalid, unverifiable, or absent.
    # "Valid" means hashes and signature verify - never that content is truthful or the signer trusted.
    status: Literal["valid", "invalid", "unverifiable", "absent"] | None = None
    validation_state: str | None = None
    manifest_count: int | None = None
    active_manifest: str | None = None
    manifests: list[C2PAManifestInfo] = []
    validation_codes: dict[str, list[dict[str, str | None]]] | None = None
    validator: str | None = None
    validator_error: str | None = None
    provenance: Provenance


class LocationCoordinate(BaseModel):
    """One coordinate pair as read (M6). `valid` is False when a value is out of range or unreadable;
    the value is still shown exactly as written."""

    source: str
    latitude: float | None
    longitude: float | None
    latitude_as_written: str | None
    longitude_as_written: str | None
    valid: bool
    problem: str | None = None


class LocationTag(BaseModel):
    """One clue exactly as written, with the tag it came from."""

    tag: str
    value: str


class LocationCluesSection(BaseModel):
    """Machine-read location clues (M6, D23): facts as written, never a location claim."""

    coordinates: list[LocationCoordinate] = []
    altitude_meters: float | None = None
    altitude_as_written: str | None = None
    altitude_reference: str | None = None
    text_clues: list[LocationTag] = []
    timestamps: list[LocationTag] = []
    device: list[LocationTag] = []
    iso6709: list[LocationTag] = []
    # True when this analysis produced OCR text the analyst can read for visible location clues.
    # Vestigo never interprets that text.
    ocr_available: bool = False
    provenance: Provenance


class StructuralFinding(BaseModel):
    """One structural observation: what, where, and how big. Never a conclusion."""

    kind: str
    offset: int
    size: int | None = None
    detail: str | None = None


class StructuralMeasurement(BaseModel):
    """One number with the method that produced it, and what it does not mean."""

    name: str
    value: float
    method: str
    note: str | None = None


class StructuralSection(BaseModel):
    """Structure and byte statistics (Pass 2, D25). Facts and measurements, never verdicts."""

    container: str | None = None
    file_size: int = 0
    # Where the format's own data ends, when the format states it.
    logical_end: int | None = None
    trailing_bytes: int = 0
    findings: list[StructuralFinding] = []
    inventory: list[dict[str, Any]] = []
    measurements: list[StructuralMeasurement] = []
    # How far structural parsing reached; not problems.
    notes: list[str] = []
    warnings: list[str] = []
    binwalk_ran: bool = False
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


class ContainerInfo(BaseModel):
    format_name: str | None
    format_long_name: str | None
    # As written in the container (decision M3-8), not measured by decoding.
    duration_seconds: float | None
    size_bytes: int | None
    bit_rate: int | None
    stream_count: int


class VideoStreamInfo(BaseModel):
    index: int | None
    codec: str | None
    profile: str | None
    width: int | None
    height: int | None
    frame_rate: float | None
    bit_rate: int | None
    pixel_format: str | None
    rotation: int | None


class AudioStreamInfo(BaseModel):
    """Header-level audio facts only (decision M3-7): nothing is decoded or transcribed."""

    index: int | None
    codec: str | None
    profile: str | None
    channels: int | None
    channel_layout: str | None
    sample_rate: int | None
    bit_rate: int | None


class OtherStreamInfo(BaseModel):
    index: int | None
    codec_type: str | None
    codec: str | None


class MediaInfoSection(BaseModel):
    container: ContainerInfo
    video_streams: list[VideoStreamInfo]
    audio_streams: list[AudioStreamInfo]
    other_streams: list[OtherStreamInfo]
    provenance: Provenance


class SceneChangeInfo(BaseModel):
    # Presentation time in seconds and ffmpeg's frame-difference score (0-1).
    time: float
    score: float


class SceneChangesSection(BaseModel):
    threshold: float | None
    count: int
    changes: list[SceneChangeInfo]
    provenance: Provenance


class KeyframeInfo(BaseModel):
    seq: int
    # Presentation time in seconds.
    timestamp: float
    # Why the frame was selected: first_frame, scene_change, or uniform_sample.
    reason: str
    scene_score: float | None = None
    # The stored thumbnail, served by GET /artifacts/{id}/derived/{derived_file_id}/content.
    derived_file_id: str | None = None
    width: int | None = None
    height: int | None = None


class KeyframesSection(BaseModel):
    policy: dict[str, Any]
    requested: int
    extracted: int
    frames: list[KeyframeInfo]
    provenance: Provenance


class KeyframeHashInfo(BaseModel):
    seq: int
    timestamp: float
    value: str
    derived_file_id: str | None = None


class KeyframePHashSection(BaseModel):
    algorithm: Literal["pHash"] = "pHash"
    bits: int
    count: int
    frames: list[KeyframeHashInfo]
    provenance: Provenance


class KeyframeOCRFrame(BaseModel):
    """One analysed keyframe's OCR result, with the image OCR stage's full detail (D13)."""

    seq: int
    timestamp: float
    text: str
    cleaned_text: str | None = None
    cleaning: list[OCRCleaningRule] = []
    confidence: float | None
    word_count: int
    preprocessing: list[OCRPreprocessingStep] = []
    candidates: list[OCRCandidate] = []
    selected: OCRSelection | None = None


class KeyframeOCRSection(BaseModel):
    engine: Literal["tesseract"] = "tesseract"
    languages: list[str]
    frame_limit: int
    analyzed: int
    frames: list[KeyframeOCRFrame]
    provenance: Provenance


class FrameMatchInfo(BaseModel):
    """One matching hash pair (M3-4). Frame fields are null for the whole-image side of a pair."""

    distance: int
    similarity: float
    query_seq: int | None = None
    query_timestamp: float | None = None
    matched_seq: int | None = None
    matched_timestamp: float | None = None
    # How the query frame was oriented for the pairing (D19): degrees counter-clockwise plus
    # mirroring; 0/false means the upright frames matched. Absent on records made before D19.
    rotation_degrees: int = 0
    mirrored: bool = False


class DuplicateMatch(BaseModel):
    artifact_id: str
    # Current filename, or None if the matched artifact has since been deleted.
    filename: str | None
    available: bool
    similarity: float
    distance: int
    match_type: Literal["exact_file", "visually_identical", "near"]
    media_type: MediaType | None = None
    # Frame detail when either side is a video (M3-4): the best counterpart per query hash. Null for
    # image-to-image and byte-identical matches.
    matched_frame_count: int | None = None
    frame_matches: list[FrameMatchInfo] | None = None


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
    # 1.1 (Milestone 2) added record-level review in `provenance` and `review_history`; 1.2
    # (Milestone 3) adds the video sections, null for image jobs; nothing removed.
    schema_version: Literal["1.2"] = "1.2"
    artifact_id: str
    job_id: str
    created_at: datetime
    notice: str = REPORT_NOTICE
    artifact: ArtifactSummary
    job: JobSummary
    hashes: HashesSection | None
    metadata: MetadataSection | None
    c2pa: C2PASection | None
    location_clues: LocationCluesSection | None
    structural: StructuralSection | None
    perceptual_hash: PerceptualHashSection | None
    ocr: OCRSection | None
    duplicates: DuplicatesSection | None
    # Video sections (Milestone 3); null for image jobs, as image sections are null for video jobs.
    media_info: MediaInfoSection | None = None
    scene_changes: SceneChangesSection | None = None
    keyframes: KeyframesSection | None = None
    keyframe_phash: KeyframePHashSection | None = None
    keyframe_ocr: KeyframeOCRSection | None = None
    review: ReviewInfo
    # Analyst-recorded external search leads (M5), newest first; artifact-level like the history.
    external_leads: list[ExternalLeadInfo] = []
    # Analyst-stated possible locations (M6), newest first.
    location_candidates: list[LocationCandidateInfo] = []
    # Every review change for this artifact, artifact- and record-level, newest first.
    review_history: list[ReviewEventOut] = []
