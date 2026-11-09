// Mirrors the Pydantic schemas in app/schemas/.

export type MediaType = "image" | "video" | "audio" | "document";

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
  /** Container-reported duration for videos (M3-8); null for images. */
  duration_seconds: number | null;
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
  /** True when a re-encoded viewing copy exists (D19); videos only. */
  has_playable_preview: boolean;
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
export type SupportedMimeType =
  | "image/jpeg"
  | "image/png"
  | "image/webp"
  | "image/tiff"
  | "video/mp4"
  | "video/quicktime"
  | "video/webm"
  | "video/x-matroska"
  | "video/x-msvideo"
  | "video/mp2t"
  | "video/x-ms-wmv"
  | "video/x-flv"
  | "video/3gpp"
  | "video/x-m4v"
  | "video/ogg"
  | "audio/wav"
  | "audio/mpeg"
  | "audio/flac"
  | "audio/ogg"
  | "audio/mp4";

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
  custody_events?: number;
  external_leads?: number;
  location_candidates?: number;
  ai_drafts?: number;
  transcripts?: number;
  embedding_chunks?: number;
  case_links?: number;
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

/** Video analysis options; keyframe OCR is off by default (M3-3). */
export interface VideoAnalysisOptions {
  metadata: boolean;
  c2pa: boolean;
  location_clues: boolean;
  structural: boolean;
  forensic_indicators: boolean;
  scene_detection: boolean;
  keyframe_ocr: boolean;
  duplicate_search: boolean;
}

/** Audio options (D19): header-level stages only; no audio is ever decoded. */
export interface AudioAnalysisOptions {
  metadata: boolean;
  c2pa: boolean;
  location_clues: boolean;
  structural: boolean;
  duplicate_search: boolean;
}

/** Document options (Pass 2). Nothing in a PDF is ever rendered or executed. */
export interface DocumentAnalysisOptions {
  metadata: boolean;
  pdf_structure: boolean;
  pdf_text: boolean;
  pdf_images: boolean;
  structural: boolean;
  duplicate_search: boolean;
}

export interface AnalysisOptions {
  metadata: boolean;
  c2pa: boolean;
  location_clues: boolean;
  structural: boolean;
  forensic_indicators: boolean;
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

/**
 * Vestigo's summary of the validator outcome (M4). "valid" means the manifest's hashes and claim
 * signature verify — never that the content is truthful or the signer trusted.
 */
export type C2PAStatus = "valid" | "invalid" | "unverifiable" | "absent";

/** One manifest as summarized by the validator (M4). */
export interface C2PAManifestInfo {
  label: string;
  title: string | null;
  claim_generator: string | null;
  signature_issuer: string | null;
  signature_common_name: string | null;
  signature_cert_serial: string | null;
  signature_time: string | null;
  signature_algorithm: string | null;
  assertion_labels: string[];
  ingredient_count: number;
}

export interface C2PAValidationCode {
  code: string | null;
  explanation: string | null;
}

/** Grouped by the validator: "success", "informational", and "failure". */
export type C2PAValidationCodes = Record<string, C2PAValidationCode[]>;

export interface C2PASection {
  present: boolean | null;
  /** False on records made before Milestone 4, which detected manifests without validating them. */
  validation_performed: boolean;
  manifest_labels: string[];
  details: C2PADetails;
  /** All null on pre-M4 detection-only records. */
  status: C2PAStatus | null;
  validation_state: string | null;
  manifest_count: number | null;
  active_manifest: string | null;
  manifests: C2PAManifestInfo[];
  validation_codes: C2PAValidationCodes | null;
  validator: string | null;
  validator_error: string | null;
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

/** One matching hash pair (M3-4). Frame fields are null for the whole-image side. */
export interface FrameMatchInfo {
  distance: number;
  similarity: number;
  query_seq: number | null;
  query_timestamp: number | null;
  matched_seq: number | null;
  matched_timestamp: number | null;
  /** How the query frame was oriented for the pairing (D19); 0/false = upright match. */
  rotation_degrees: number;
  mirrored: boolean;
}

export interface DuplicateMatch {
  artifact_id: string;
  filename: string | null;
  available: boolean;
  media_type: MediaType | null;
  similarity: number;
  distance: number;
  match_type: MatchType;
  /** Frame detail when either side is a video; null for image-to-image and exact-file matches. */
  matched_frame_count: number | null;
  frame_matches: FrameMatchInfo[] | null;
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
  schema_version: "1.2";
  artifact_id: string;
  job_id: string;
  created_at: string;
  notice: string;
  artifact: ArtifactSummary;
  job: JobSummary;
  hashes: HashesSection | null;
  metadata: MetadataSection | null;
  c2pa: C2PASection | null;
  location_clues: LocationCluesSection | null;
  structural: StructuralSection | null;
  forensic_indicators: ForensicIndicatorsSection | null;
  pdf_structure: PdfStructureSection | null;
  pdf_text: PdfTextSection | null;
  pdf_images: PdfImagesSection | null;
  perceptual_hash: PerceptualHashSection | null;
  ocr: OCRSection | null;
  duplicates: DuplicatesSection | null;
  media_info: MediaInfoSection | null;
  scene_changes: SceneChangesSection | null;
  keyframes: KeyframesSection | null;
  keyframe_phash: KeyframePHashSection | null;
  keyframe_ocr: KeyframeOCRSection | null;
  review: ReviewInfo;
  /** Newest first. */
  review_history: ReviewEvent[];
  /** Analyst-recorded external search leads (M5), newest first. */
  external_leads: ExternalLead[];
  /** Analyst-stated possible locations (M6), newest first. */
  location_candidates: LocationCandidate[];
  /** Cases this artifact was put in (Pass 3). Organisation, not evidence. */
  cases: { case_id: string; name: string }[];
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
  default_video_analysis_options: VideoAnalysisOptions;
  default_audio_analysis_options: AudioAnalysisOptions;
  default_document_analysis_options: DocumentAnalysisOptions;
  library_page_size: LibraryPageSize;
  auto_analyze_after_upload: boolean;
  /** Reverse-image search providers the analyst enabled (M5). All disabled by default. */
  enabled_search_providers: string[];
  /** Off by default (M6): when on, the artifact page offers an external OpenStreetMap link. */
  enable_external_map_links: boolean;
  /** Local AI (Pass 1). All off by default; nothing is downloaded or sent anywhere. */
  ai_enabled: boolean;
  transcription_enabled: boolean;
  semantic_search_enabled: boolean;
  /** Read-only integration surface (Pass 3). Off by default; it can never write anything. */
  integration_api_enabled: boolean;
  ai_model_path: string;
  transcription_model_path: string;
}

/** Read-only: set with VESTIGO_* environment variables or .env. */
export interface EnvironmentSettings {
  data_dir: string;
  max_upload_bytes: number;
  max_image_pixels: number;
  duplicate_threshold: number;
  max_video_upload_bytes: number;
  max_video_duration_seconds: number;
  max_video_pixels: number;
  max_keyframes: number;
  scene_threshold: number;
  video_timeout_seconds: number;
  max_audio_upload_bytes: number;
  max_audio_duration_seconds: number;
  max_document_upload_bytes: number;
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

// --- Video sections (Milestone 3) ---------------------------------------------------------------

export interface ContainerInfo {
  format_name: string | null;
  format_long_name: string | null;
  /** As written in the container (M3-8), not measured by decoding. */
  duration_seconds: number | null;
  size_bytes: number | null;
  bit_rate: number | null;
  stream_count: number;
}

export interface VideoStreamInfo {
  index: number | null;
  codec: string | null;
  profile: string | null;
  width: number | null;
  height: number | null;
  frame_rate: number | null;
  bit_rate: number | null;
  pixel_format: string | null;
  rotation: number | null;
}

/** Header-level audio facts only (M3-7): nothing is decoded or transcribed. */
export interface AudioStreamInfo {
  index: number | null;
  codec: string | null;
  profile: string | null;
  channels: number | null;
  channel_layout: string | null;
  sample_rate: number | null;
  bit_rate: number | null;
}

export interface MediaInfoSection {
  container: ContainerInfo;
  video_streams: VideoStreamInfo[];
  audio_streams: AudioStreamInfo[];
  other_streams: { index: number | null; codec_type: string | null; codec: string | null }[];
  provenance: Provenance;
}

export interface SceneChangeInfo {
  time: number;
  score: number;
}

export interface SceneChangesSection {
  threshold: number | null;
  count: number;
  changes: SceneChangeInfo[];
  provenance: Provenance;
}

export interface KeyframeInfo {
  seq: number;
  timestamp: number;
  reason: "first_frame" | "scene_change" | "uniform_sample" | string;
  scene_score: number | null;
  derived_file_id: string | null;
  width: number | null;
  height: number | null;
}

export interface KeyframesSection {
  policy: Record<string, unknown>;
  requested: number;
  extracted: number;
  frames: KeyframeInfo[];
  provenance: Provenance;
}

export interface KeyframeHashInfo {
  seq: number;
  timestamp: number;
  value: string;
  derived_file_id: string | null;
}

export interface KeyframePHashSection {
  algorithm: "pHash";
  bits: number;
  count: number;
  frames: KeyframeHashInfo[];
  provenance: Provenance;
}

/** One analysed keyframe's OCR result, with the image OCR stage's detail (D13). */
export interface KeyframeOCRFrame {
  seq: number;
  timestamp: number;
  text: string;
  cleaned_text: string | null;
  cleaning: OCRCleaningRule[];
  confidence: number | null;
  word_count: number;
  preprocessing: OCRPreprocessingStep[];
  candidates: OCRCandidate[];
  selected: { variant: OCRVariant; reason: string } | null;
}

export interface KeyframeOCRSection {
  engine: "tesseract";
  languages: string[];
  frame_limit: number;
  analyzed: number;
  frames: KeyframeOCRFrame[];
  provenance: Provenance;
}

/** A re-encoded viewing copy of a video (D19). Not evidence; excluded from the export package. */
export interface PreviewInfo {
  artifact_id: string;
  sha256: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  created_at: string;
}

// --- Chain of custody (Milestone 4 part 2) -------------------------------------------------------

/** One recorded action. `source_table` names where the fact lives; nothing is inferred. */
export interface CustodyTimelineEvent {
  type: string;
  at: string;
  source_table: string;
  detail: Record<string, unknown>;
}

/**
 * One derived file with its recorded lineage. A null `source_kind` means the row was written
 * before schema revision 0005 and its source was not recorded — never guessed.
 */
export interface CustodyDerivedFile {
  derived_file_id: string;
  job_id: string;
  stage: string;
  kind: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  created_at: string;
  source_kind: "original" | "derived_file" | null;
  source_derived_file_id: string | null;
}

export interface CustodyReport {
  artifact_id: string;
  notice: string;
  events: CustodyTimelineEvent[];
  derived_files: CustodyDerivedFile[];
}

// --- Reverse-image search (Milestone 5) -----------------------------------------------------------

export interface SearchProviderInfo {
  key: string;
  name: string;
  landing_url: string;
  terms_url: string;
  instructions: string;
  /** Set by the analyst in Settings; every provider starts disabled. */
  enabled: boolean;
}

export interface SearchProvidersResponse {
  /** The sharing warning, shown before any provider page is opened. */
  notice: string;
  providers: SearchProviderInfo[];
}

/**
 * One analyst-recorded external result. URLs and the claimed publication date are stored exactly
 * as entered and never verified; recorded_at is when Vestigo saved the lead.
 */
export interface ExternalLead {
  lead_id: string;
  artifact_id: string;
  derived_file_id: string | null;
  provider: string;
  result_url: string;
  image_url: string | null;
  claimed_published_at: string | null;
  notes: string;
  classification: "EXTERNAL";
  review_state: ReviewState;
  recorded_at: string;
  updated_at: string | null;
}

export interface ExternalLeadsResponse {
  artifact_id: string;
  notice: string;
  leads: ExternalLead[];
}

export interface ExternalLeadCreate {
  provider: string;
  result_url: string;
  image_url?: string;
  claimed_published_at?: string;
  notes?: string;
  derived_file_id?: string;
}

export interface ExternalLeadUpdate {
  provider?: string;
  result_url?: string;
  image_url?: string;
  claimed_published_at?: string;
  notes?: string;
  review_state?: ReviewState;
}

// --- Location clues and candidates (Milestone 6) --------------------------------------------------

/**
 * One coordinate pair as read (M6). `valid` is false when a value is out of range or only half
 * present; the value is still shown exactly as written.
 */
export interface LocationCoordinate {
  source: string;
  latitude: number | null;
  longitude: number | null;
  latitude_as_written: string | null;
  longitude_as_written: string | null;
  valid: boolean;
  problem: string | null;
}

/** One clue exactly as written, with the tag it came from. */
export interface LocationTag {
  tag: string;
  value: string;
}

/** Machine-read location clues: facts as written, never a location claim. */
export interface LocationCluesSection {
  coordinates: LocationCoordinate[];
  altitude_meters: number | null;
  altitude_as_written: string | null;
  altitude_reference: string | null;
  text_clues: LocationTag[];
  timestamps: LocationTag[];
  device: LocationTag[];
  iso6709: LocationTag[];
  /** True when this analysis produced OCR text the analyst can read. Vestigo never interprets it. */
  ocr_available: boolean;
  provenance: Provenance;
}

/** The analyst's own judgment, never a machine score. */
export type AnalystAssessment = "speculative" | "possible" | "likely";

export type SupportType = "evidence_record" | "derived_file" | "external_lead";

export interface SupportRef {
  type: SupportType;
  id: string;
}

/**
 * One possible location stated by the analyst (M6), classified UNVERIFIED. Everything here is the
 * analyst's statement; `recorded_at` is when Vestigo saved it.
 */
export interface LocationCandidate {
  candidate_id: string;
  artifact_id: string;
  description: string;
  latitude: number | null;
  longitude: number | null;
  basis: string;
  notes: string;
  analyst_assessment: AnalystAssessment;
  supports: SupportRef[];
  classification: "UNVERIFIED";
  review_state: ReviewState;
  recorded_at: string;
  updated_at: string | null;
}

export interface LocationCandidatesResponse {
  artifact_id: string;
  notice: string;
  candidates: LocationCandidate[];
}

export interface LocationCandidateCreate {
  description: string;
  basis: string;
  analyst_assessment: AnalystAssessment;
  latitude?: number | null;
  longitude?: number | null;
  notes?: string;
  supports?: SupportRef[];
}

export interface LocationCandidateUpdate {
  description?: string;
  basis?: string;
  analyst_assessment?: AnalystAssessment;
  latitude?: number | null;
  longitude?: number | null;
  notes?: string;
  supports?: SupportRef[];
  review_state?: ReviewState;
}

// --- Local AI (Pass 1) ---------------------------------------------------------------------------

export interface AIModelInfo {
  name: string;
  version: string | null;
  quantization: string | null;
  source_url: string | null;
  license: string | null;
  runtime: string;
  generation: number | null;
  local_path: string | null;
  size_bytes: number | null;
  sha256: string | null;
  installed: boolean;
  /** Whether the engine that would load this model is staged here. Separate from `installed`. */
  runnable: boolean;
  unavailable_reason: string | null;
}

/** A model file staged on this machine, as measured on disk (D27). */
export interface ManagedModelInfo {
  name: string;
  size_bytes: number;
  sha256: string;
  modified_at: string;
  path: string;
  configured_for: string[];
}

export interface ManagedModelsResponse {
  models: ManagedModelInfo[];
  models_directory: string;
  notice: string;
  limitations: string[];
}

export interface AIStatus {
  runtime_package: string;
  runtime_installed: boolean;
  telemetry_disabled: boolean;
  telemetry_environment: Record<string, string>;
  /** Downloads are blocked in-process, so the runtime cannot fetch an engine or weights. */
  offline_enforced: boolean;
  offline_environment: Record<string, string>;
  engine_generation: number;
  engine_available: boolean;
  engine_path: string | null;
  engine_unavailable_reason: string | null;
  ai_enabled: boolean;
  transcription_enabled: boolean;
  semantic_search_enabled: boolean;
  drafts_available: boolean;
  drafts_unavailable_reason: string | null;
  transcription_available: boolean;
  transcription_unavailable_reason: string | null;
  semantic_search_available: boolean;
  semantic_search_unavailable_reason: string | null;
  label: string;
  limitations: string[];
  known_models: AIModelInfo[];
}

export type DraftSource = "ocr_text" | "analyst_notes" | "metadata" | "transcript";
export type FieldAction = "accepted" | "edited" | "rejected";

export interface DraftField {
  name: string;
  /** The model's own value, kept even after an edit or rejection. */
  value: string;
  /** Only ever the model's own figure; Vestigo never calculates one. */
  confidence: number | null;
  status: "proposed" | FieldAction;
  edited_value: string | null;
}

export interface AIDraft {
  draft_id: string;
  artifact_id: string;
  kind: string;
  source_kind: string;
  source_evidence_id: string | null;
  fields: DraftField[];
  status: string;
  model: Record<string, unknown>;
  reasoning: string | null;
  warnings: string[];
  created_at: string;
  updated_at: string | null;
}

export interface AIDraftsResponse {
  artifact_id: string;
  notice: string;
  label: string;
  drafts: AIDraft[];
}

export interface TranscriptSegmentInfo {
  start: number;
  end: number;
  text: string;
  words: Record<string, unknown>[];
}

export interface Transcript {
  transcript_id: string;
  artifact_id: string;
  derived_file_id: string | null;
  language: string | null;
  duration_seconds: number | null;
  /** The model's text, kept verbatim. */
  text: string;
  edited_text: string | null;
  segments: TranscriptSegmentInfo[];
  model: Record<string, unknown>;
  warnings: string[];
  review_state: ReviewState;
  created_at: string;
  updated_at: string | null;
}

export interface TranscriptsResponse {
  artifact_id: string;
  notice: string;
  transcripts: Transcript[];
}

export interface IndexResult {
  artifact_id: string;
  chunks: number;
  model: string | null;
  sources: string[];
}

export interface SearchHit {
  artifact_id: string;
  filename: string | null;
  media_type: string | null;
  source_kind: string;
  source_ref: string | null;
  score: number;
  text: string;
}

export interface SemanticSearchResponse {
  query: string;
  hits: SearchHit[];
  model: string | null;
}

export interface AnswerResponse {
  question: string;
  /** Always present: the analyst's own material the answer was drawn from. */
  sources: SearchHit[];
  /** Absent when no local generator is available. */
  answer: string | null;
  notice: string;
  label: string;
}

// --- Structure, forensic indicators, and documents (Pass 2) --------------------------------------

/** One structural observation: what, where, how big. Never a conclusion. */
export interface StructuralFinding {
  kind: string;
  offset: number;
  size: number | null;
  detail: string | null;
}

/** One number with the method that produced it, and what it does not mean. */
export interface StructuralMeasurement {
  name: string;
  value: number;
  method: string;
  note: string | null;
}

export interface StructuralSection {
  container: string | null;
  file_size: number;
  logical_end: number | null;
  trailing_bytes: number;
  findings: StructuralFinding[];
  inventory: Record<string, unknown>[];
  measurements: StructuralMeasurement[];
  /** How far structural parsing reached; not problems. */
  notes: string[];
  warnings: string[];
  binwalk_ran: boolean;
  provenance: Provenance;
}

export interface QuantizationTableInfo {
  index: number;
  precision: number;
  values: number[];
  /** The IJG quality whose standard table is closest. An estimate of the LAST save only. */
  implied_quality: number | null;
  matches_standard: boolean;
}

export interface ForensicIndicatorsSection {
  container: string | null;
  quantization_tables: QuantizationTableInfo[];
  channel_statistics: Record<string, number | string>[];
  decoded_width: number | null;
  decoded_height: number | null;
  declared_width: number | null;
  declared_height: number | null;
  /** Whether the metadata's dimensions match the decoded pixels. A fact, not an accusation. */
  dimensions_match: boolean | null;
  video_statistics: Record<string, unknown>;
  notes: string[];
  warnings: string[];
  provenance: Provenance;
}

export interface PdfStructureSection {
  pdf_version: string | null;
  file_size: number;
  object_count: number;
  page_count: number;
  eof_markers: number;
  startxref_markers: number;
  /** More than zero means the file was saved more than once: ordinary, not suspicious. */
  incremental_updates: number;
  encrypted: boolean;
  markers: Record<string, number>;
  /** Signature dictionaries present. Vestigo never validates a PDF signature. */
  signature_count: number;
  linearized: boolean;
  notes: string[];
  warnings: string[];
  provenance: Provenance;
}

export interface PdfTextSection {
  text: string;
  character_count: number;
  streams_read: number;
  streams_skipped: number;
  streams_failed: number;
  notes: string[];
  provenance: Provenance;
}

export interface PdfEmbeddedImage {
  index: number;
  encoding: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  derived_file_id: string | null;
}

export interface PdfImagesSection {
  images: PdfEmbeddedImage[];
  extracted: number;
  notes: string[];
  provenance: Provenance;
}

// --- Cases and geospatial tools (Pass 3) ---------------------------------------------------------

export interface CaseArtifactRef {
  artifact_id: string;
  filename: string | null;
  media_type: string | null;
  added_at: string;
}

/** A case groups artifacts under a name. Organisation, never evidence. */
export interface CaseInfo {
  case_id: string;
  name: string;
  notes: string;
  artifact_count: number;
  artifacts: CaseArtifactRef[];
  created_at: string;
  updated_at: string | null;
}

export interface CasesResponse {
  notice: string;
  cases: CaseInfo[];
}

export interface CoordinateFormatsInfo {
  decimal: string;
  degrees_minutes_seconds: string;
  degrees_decimal_minutes: string;
  iso6709: string;
}

export interface CoordinatePoint {
  source: string;
  latitude: number;
  longitude: number;
  formats: CoordinateFormatsInfo;
  candidate_id: string | null;
}

export interface CoordinatePair {
  from_source: string;
  to_source: string;
  distance_metres: number;
  bearing_degrees: number;
}

export interface GeoToolsResponse {
  artifact_id: string;
  notice: string;
  points: CoordinatePoint[];
  pairs: CoordinatePair[];
  limitations: string[];
  offline_map_available: boolean;
  offline_map_path: string | null;
}
