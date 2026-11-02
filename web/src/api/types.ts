// Mirrors the Pydantic schemas in app/schemas/.

export type MediaType = "image";

export type ReviewState = "UNREVIEWED" | "IN_REVIEW" | "REVIEWED" | "FLAGGED" | "ARCHIVED";
export const REVIEW_STATES: ReviewState[] = ["UNREVIEWED", "IN_REVIEW", "REVIEWED", "FLAGGED", "ARCHIVED"];

export type EvidenceClassification = "OBSERVED" | "DERIVED" | "EXTERNAL" | "UNVERIFIED" | "REVIEWED";
export type JobStatus = "queued" | "running" | "completed" | "completed_with_errors" | "failed";
export type StageStatus = "pending" | "running" | "succeeded" | "partial" | "failed" | "skipped";

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface ArtifactUploadResponse {
  artifact_id: string;
  filename: string;
  size_bytes: number;
  media_type: MediaType;
  mime_type: string;
  sha256: string;
  created_at: string;
}

export interface ReviewInfo {
  state: ReviewState;
  analyst_notes: string;
  updated_at: string;
}

export interface JobSummary {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ArtifactSummary {
  artifact_id: string;
  filename: string;
  media_type: MediaType;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  review_state: ReviewState;
  latest_job_status: JobStatus | null;
}

export interface ArtifactDetail extends ArtifactSummary {
  sha256: string;
  md5: string;
  width: number | null;
  height: number | null;
  review: ReviewInfo;
  latest_job: JobSummary | null;
}

export interface ArtifactList {
  items: ArtifactSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface DeletionSummary {
  artifact_id: string;
  original_files: number;
  derived_files: number;
  jobs: number;
  evidence_records: number;
}

export interface AnalysisOptions {
  metadata: boolean;
  c2pa: boolean;
  ocr: boolean;
  duplicate_search: boolean;
}

export interface JobCreated {
  job_id: string;
  artifact_id: string;
  status: JobStatus;
}

export interface StageProgress {
  stage: string;
  status: StageStatus;
  started_at: string | null;
  completed_at: string | null;
}

export interface JobStatusResponse extends JobSummary {
  artifact_id: string;
  pipeline: string;
  error: ApiErrorBody | null;
  stages: StageProgress[];
}

export interface StageError {
  type: string;
  message: string;
}

export interface DerivedFileInfo {
  derived_file_id: string;
  kind: string;
  sha256: string;
  size_bytes: number;
}

export interface Provenance {
  evidence_id: string;
  stage: string;
  status: StageStatus;
  classification: EvidenceClassification;
  method: string;
  source: string;
  tool: string;
  tool_version: string | null;
  started_at: string;
  completed_at: string;
  limitations: string[];
  errors: StageError[];
  review_state: ReviewState;
  skip_reason: string | null;
  derived_files: DerivedFileInfo[];
}

export type TagGroups = Record<string, Record<string, unknown>>;

export interface HashesSection {
  sha256: string | null;
  md5: string | null;
  matches_upload_record: boolean | null;
  provenance: Provenance;
}

export interface MetadataSection {
  exif: TagGroups;
  xmp: TagGroups;
  iptc: TagGroups;
  other: TagGroups;
  composite: TagGroups;
  provenance: Provenance;
}

export interface C2PAManifest {
  label: string | null;
  jumbf_type: string | null;
  claim: Record<string, unknown>;
  assertions: string[];
  assertion_data: Record<string, Record<string, unknown>>;
  signature_present: boolean;
}

export interface C2PADetails {
  detectors?: {
    byte_scan?: { found: boolean; container: string | null; segments: number; bytes: number };
    exiftool?: { found: boolean; jumbf_boxes: number };
  };
  manifests?: C2PAManifest[];
  active_manifest_label?: string | null;
  xmp_provenance?: string | null;
}

export interface C2PASection {
  present: boolean | null;
  validation_performed: false;
  manifest_labels: string[];
  details: C2PADetails;
  provenance: Provenance;
}

export interface PerceptualHashSection {
  algorithm: "pHash";
  bits: number;
  value: string | null;
  provenance: Provenance;
}

export interface OCRSection {
  engine: "tesseract";
  languages: string[];
  text: string;
  confidence: number | null;
  word_count: number;
  provenance: Provenance;
}

export type MatchType = "exact_file" | "visually_identical" | "near";

export interface DuplicateMatch {
  artifact_id: string;
  filename: string | null;
  available: boolean;
  similarity: number;
  distance: number;
  match_type: MatchType;
}

export interface DuplicatesSection {
  algorithm: "pHash";
  threshold: number | null;
  library_size: number | null;
  compared: number | null;
  matches: DuplicateMatch[];
  provenance: Provenance;
}

export interface EvidenceReport {
  schema_version: "1.0";
  artifact_id: string;
  job_id: string;
  created_at: string;
  notice: string;
  artifact: ArtifactSummary;
  job: JobSummary;
  hashes: HashesSection | null;
  metadata: MetadataSection | null;
  c2pa: C2PASection | null;
  perceptual_hash: PerceptualHashSection | null;
  ocr: OCRSection | null;
  duplicates: DuplicatesSection | null;
  review: ReviewInfo;
}
