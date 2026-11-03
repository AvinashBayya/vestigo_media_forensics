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

/** An artifact with indicators for its latest analysis job (app/services/library.py). */
export interface ArtifactListItem extends ArtifactSummary {
  latest_job: JobSummary | null;
  /** Failed or partial stages in the latest job, plus one if the job failed. Null if never analysed. */
  problem_count: number | null;
  /** Matches in the latest duplicate search. Null if that search produced no result. */
  duplicate_match_count: number | null;
  /** Library artifacts uploaded after that search finished. Null if there is no search result. */
  added_since_analysis: number | null;
  in_duplicate_library: boolean;
}

export interface ArtifactDetail extends ArtifactListItem {
  sha256: string;
  md5: string;
  width: number | null;
  height: number | null;
  review: ReviewInfo;
}

export interface ArtifactList {
  items: ArtifactListItem[];
  total: number;
  limit: number;
  offset: number;
  counts_by_review_state: Record<ReviewState, number>;
}

export type AnalysisStatusFilter = JobStatus | "not_analysed";
export type ArtifactSort = "created_at" | "filename" | "size_bytes" | "review_state";
export type SortOrder = "asc" | "desc";
export type SupportedMimeType = "image/jpeg" | "image/png" | "image/webp" | "image/tiff";

/** Query parameters of GET /artifacts. All optional. */
export interface ArtifactQuery {
  q?: string;
  review_state?: ReviewState[];
  analysis_status?: AnalysisStatusFilter[];
  has_problems?: boolean;
  has_duplicates?: boolean;
  mime_type?: SupportedMimeType[];
  uploaded_from?: string;
  uploaded_to?: string;
  include_archived?: boolean;
  sort?: ArtifactSort;
  order?: SortOrder;
  limit?: number;
  offset?: number;
}

export interface DeletionSummary {
  artifact_id: string;
  original_files: number;
  derived_files: number;
  jobs: number;
  evidence_records: number;
  review_events: number;
}

export type ReviewOrigin = "artifact" | "record" | "bulk";

/** One review change. Append-only, with the full note text before and after (M2-3). */
export interface ReviewEvent {
  event_id: string;
  origin: ReviewOrigin;
  evidence_id: string | null;
  stage: string | null;
  job_id: string | null;
  from_state: ReviewState;
  to_state: ReviewState;
  notes_before: string;
  notes_after: string;
  created_at: string;
}

export interface ReviewHistory {
  artifact_id: string;
  events: ReviewEvent[];
}

export interface RecordReview {
  evidence_id: string;
  artifact_id: string;
  job_id: string;
  stage: string;
  classification: EvidenceClassification;
  review_state: ReviewState;
  analyst_notes: string;
  review_updated_at: string | null;
}

export interface BulkReviewResult {
  state: ReviewState;
  updated: string[];
  unchanged: string[];
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
  /** Record-level review by the analyst (M2-2). */
  analyst_notes: string;
  review_updated_at: string | null;
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

export type OCRVariant = "grayscale" | "threshold";

export interface OCRPreprocessingStep {
  step: string;
  applied: boolean;
  description: string;
  parameters: Record<string, unknown>;
}

export interface OCRCandidate {
  variant: OCRVariant;
  status: "succeeded" | "failed";
  text: string | null;
  confidence: number | null;
  word_count: number | null;
  error: string | null;
}

export interface OCRCleaningRule {
  rule: string;
  description: string;
  lines_affected: number;
}

export interface OCRSection {
  engine: "tesseract";
  languages: string[];
  /** Raw Tesseract text of the selected pass, unchanged. */
  text: string;
  /** Null when cleaning changed nothing, and for records made before two-pass OCR. */
  cleaned_text: string | null;
  cleaning: OCRCleaningRule[];
  confidence: number | null;
  word_count: number;
  preprocessing: OCRPreprocessingStep[];
  /** Empty, and `selected` null, for records made before two-pass OCR. */
  candidates: OCRCandidate[];
  selected: { variant: OCRVariant; reason: string } | null;
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
  /** Artifacts excluded from duplicate search by the analyst (M2-7). Null for records made before M2. */
  excluded_count: number | null;
  matches: DuplicateMatch[];
  provenance: Provenance;
}

export interface EvidenceReport {
  schema_version: "1.1";
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
  /** Newest first. */
  review_history: ReviewEvent[];
}

export interface JobHistoryItem extends JobSummary {
  pipeline: string;
  app_version: string;
  options: AnalysisOptions;
  /** Job-level failure, e.g. INTERRUPTED by a restart. */
  error: ApiErrorBody | null;
  /** Failed or partial stages, plus one if the job itself failed. */
  problem_count: number;
}

export interface JobHistory {
  artifact_id: string;
  /** Newest first. */
  jobs: JobHistoryItem[];
}

export interface ToolHealth {
  status: "ok" | "missing" | "error";
  version: string | null;
  used_in: string;
  languages: string[] | null;
  detail: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  version: string;
  database: "ok" | "error";
  storage: "ok" | "error";
  tools: Record<string, ToolHealth>;
  checked_at: string;
}

export interface LibraryArtifactRef {
  artifact_id: string;
  filename: string;
  created_at: string;
  indexed: boolean;
}

export interface LibrarySummary {
  artifact_count: number;
  indexed_count: number;
  not_indexed_count: number;
  excluded_count: number;
  not_indexed: LibraryArtifactRef[];
  excluded: LibraryArtifactRef[];
  storage: { original_bytes: number; derived_bytes: number };
}

export type LibraryPageSize = 10 | 25 | 50 | 100;
export const LIBRARY_PAGE_SIZES: LibraryPageSize[] = [10, 25, 50, 100];

export interface EditableSettings {
  default_analysis_options: AnalysisOptions;
  library_page_size: LibraryPageSize;
  auto_analyze_after_upload: boolean;
}

/** Read-only: set with VESTIGO_* environment variables or .env. */
export interface EnvironmentSettings {
  data_dir: string;
  max_upload_bytes: number;
  max_image_pixels: number;
  duplicate_threshold: number;
  job_mode: string;
  job_workers: number;
  tool_timeout_seconds: number;
  ocr_timeout_seconds: number;
  ocr_languages: string[];
  log_level: string;
  app_version: string;
  schema_revision: string | null;
}

export interface SettingsResponse {
  editable: EditableSettings;
  environment: EnvironmentSettings;
  updated_at: string | null;
}
