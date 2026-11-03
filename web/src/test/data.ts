import type {
  ArtifactDetail,
  ArtifactList,
  ArtifactListItem,
  HealthResponse,
  JobHistoryItem,
  SettingsResponse,
  EvidenceReport,
  JobStatusResponse,
  Provenance,
  StageStatus,
} from "../api/types";

export const ARTIFACT_ID = "art_11111111111111111111111111111111";
export const OTHER_ARTIFACT_ID = "art_22222222222222222222222222222222";
export const JOB_ID = "job_33333333333333333333333333333333";
const NOW = "2026-11-02T09:00:00.000000Z";

export function provenance(stage: string, overrides: Partial<Provenance> = {}): Provenance {
  return {
    evidence_id: `ev_${stage}`,
    stage,
    status: "succeeded",
    classification: "DERIVED",
    method: `Method for ${stage}.`,
    source: "artifact:original",
    tool: `${stage}-tool`,
    tool_version: "1.0",
    started_at: NOW,
    completed_at: NOW,
    limitations: [`Limitation of ${stage}.`],
    errors: [],
    review_state: "UNREVIEWED",
    skip_reason: null,
    derived_files: [],
    analyst_notes: "",
    review_updated_at: null,
    ...overrides,
  };
}

export function artifactDetail(overrides: Partial<ArtifactDetail> = {}): ArtifactDetail {
  return {
    artifact_id: ARTIFACT_ID,
    filename: "harbour.jpg",
    media_type: "image",
    mime_type: "image/jpeg",
    size_bytes: 36_000,
    created_at: NOW,
    review_state: "UNREVIEWED",
    latest_job_status: "completed",
    sha256: "a".repeat(64),
    md5: "b".repeat(32),
    width: 640,
    height: 480,
    review: { state: "UNREVIEWED", analyst_notes: "", updated_at: NOW },
    latest_job: { job_id: JOB_ID, status: "completed", created_at: NOW, started_at: NOW, completed_at: NOW },
    problem_count: 0,
    duplicate_match_count: 1,
    added_since_analysis: 0,
    in_duplicate_library: true,
    ...overrides,
  };
}

let itemCounter = 0;

/** A Library row. IDs are unique unless given. */
export function listItem(overrides: Partial<ArtifactListItem> = {}): ArtifactListItem {
  itemCounter += 1;
  const id = `art_${itemCounter.toString(16).padStart(32, "0")}`;
  return {
    artifact_id: id,
    filename: `image-${itemCounter}.jpg`,
    media_type: "image",
    mime_type: "image/jpeg",
    size_bytes: 36_000,
    created_at: NOW,
    review_state: "UNREVIEWED",
    latest_job_status: "completed",
    latest_job: { job_id: JOB_ID, status: "completed", created_at: NOW, started_at: NOW, completed_at: NOW },
    problem_count: 0,
    duplicate_match_count: 0,
    added_since_analysis: 0,
    in_duplicate_library: true,
    ...overrides,
  };
}

export function artifactList(items: ArtifactListItem[], overrides: Partial<ArtifactList> = {}): ArtifactList {
  const counts = { UNREVIEWED: 0, IN_REVIEW: 0, REVIEWED: 0, FLAGGED: 0, ARCHIVED: 0 };
  for (const item of items) counts[item.review_state] += 1;
  return { items, total: items.length, limit: 25, offset: 0, counts_by_review_state: counts, ...overrides };
}

export function jobStatus(status: JobStatusResponse["status"], stages: StageStatus[]): JobStatusResponse {
  const names = ["hashes", "metadata", "c2pa", "perceptual_hash", "ocr", "duplicates"];
  return {
    job_id: JOB_ID,
    artifact_id: ARTIFACT_ID,
    pipeline: "image.v1",
    status,
    created_at: NOW,
    started_at: NOW,
    completed_at: null,
    error: null,
    stages: names.map((stage, index) => ({
      stage,
      status: stages[index] ?? "pending",
      started_at: null,
      completed_at: null,
    })),
  };
}

export function evidenceReport(overrides: Partial<EvidenceReport> = {}): EvidenceReport {
  return {
    schema_version: "1.1",
    artifact_id: ARTIFACT_ID,
    job_id: JOB_ID,
    created_at: NOW,
    notice: "This report lists signals. It does not determine whether the media is authentic.",
    artifact: artifactDetail(),
    job: { job_id: JOB_ID, status: "completed", created_at: NOW, started_at: NOW, completed_at: NOW },
    hashes: {
      sha256: "a".repeat(64),
      md5: "b".repeat(32),
      matches_upload_record: true,
      provenance: provenance("hashes"),
    },
    metadata: {
      exif: { IFD0: { Make: "VestigoTestCam", Model: "Fixture Model 1" } },
      xmp: { "XMP-dc": { Title: "Fixture title", Creator: ["Fixture Author"] } },
      iptc: {},
      other: { File: { FileType: "JPEG" } },
      composite: { Composite: { ImageSize: "640x480" } },
      provenance: provenance("metadata", { classification: "OBSERVED", tool: "ExifTool", tool_version: "13.25" }),
    },
    c2pa: {
      present: false,
      validation_performed: false,
      manifest_labels: [],
      details: {
        detectors: {
          byte_scan: { found: false, container: "jpeg_app11", segments: 0, bytes: 0 },
          exiftool: { found: false, jumbf_boxes: 0 },
        },
        manifests: [],
        active_manifest_label: null,
        xmp_provenance: null,
      },
      provenance: provenance("c2pa", { classification: "OBSERVED" }),
    },
    perceptual_hash: {
      algorithm: "pHash",
      bits: 64,
      value: "eb1c2d708d668e63",
      provenance: provenance("perceptual_hash"),
    },
    ocr: {
      engine: "tesseract",
      languages: ["eng"],
      text: "VESTIGO EVIDENCE SAMPLE 2026",
      cleaned_text: null,
      cleaning: [],
      confidence: 0.91,
      word_count: 4,
      preprocessing: [
        { step: "grayscale", applied: true, description: "Converted to 8-bit greyscale.", parameters: { mode: "L" } },
        {
          step: "upscale",
          applied: false,
          description: "Not upscaled: the image is large enough.",
          parameters: { factor: 1 },
        },
      ],
      candidates: [
        {
          variant: "grayscale",
          status: "succeeded",
          text: "VESTIGO EVIDENCE SAMPLE 2026",
          confidence: 0.91,
          word_count: 4,
          error: null,
        },
        {
          variant: "threshold",
          status: "succeeded",
          text: "VESTIGO EVIDENCE SAMPLE 2026",
          confidence: 0.9,
          word_count: 4,
          error: null,
        },
      ],
      selected: { variant: "grayscale", reason: "The threshold pass was not used: its confidence gain was -0.01." },
      provenance: provenance("ocr", { tool: "Tesseract", tool_version: "5.5.0; Pillow 13.0.0" }),
    },
    duplicates: {
      algorithm: "pHash",
      threshold: 10,
      library_size: 2,
      compared: 1,
      excluded_count: 0,
      matches: [
        {
          artifact_id: OTHER_ARTIFACT_ID,
          filename: "harbour-copy.jpg",
          available: true,
          similarity: 1,
          distance: 0,
          match_type: "exact_file",
        },
      ],
      provenance: provenance("duplicates"),
    },
    review: { state: "UNREVIEWED", analyst_notes: "", updated_at: NOW },
    review_history: [],
    ...overrides,
  };
}

export function jobHistoryItem(overrides: Partial<JobHistoryItem> = {}): JobHistoryItem {
  return {
    job_id: JOB_ID,
    status: "completed",
    created_at: NOW,
    started_at: NOW,
    completed_at: NOW,
    pipeline: "image.v1",
    app_version: "0.1.0",
    options: { metadata: true, c2pa: true, ocr: true, duplicate_search: true },
    error: null,
    problem_count: 0,
    ...overrides,
  };
}

export function health(overrides: Partial<HealthResponse> = {}): HealthResponse {
  const tool = { status: "ok" as const, version: "1", used_in: "M1", languages: null, detail: null };
  return {
    status: "ok",
    version: "0.1.0",
    database: "ok",
    storage: "ok",
    tools: { exiftool: tool, tesseract: { ...tool, languages: ["eng"] }, ffmpeg: tool, ffprobe: tool },
    checked_at: NOW,
    ...overrides,
  };
}

export function settingsResponse(editable: Partial<SettingsResponse["editable"]> = {}): SettingsResponse {
  return {
    editable: {
      default_analysis_options: { metadata: true, c2pa: true, ocr: true, duplicate_search: true },
      library_page_size: 25,
      auto_analyze_after_upload: true,
      ...editable,
    },
    environment: {
      data_dir: "/workspaces/vestigo-media-forensics/data",
      max_upload_bytes: 52_428_800,
      max_image_pixels: 100_000_000,
      duplicate_threshold: 10,
      job_mode: "thread",
      job_workers: 2,
      tool_timeout_seconds: 60,
      ocr_timeout_seconds: 120,
      ocr_languages: ["eng"],
      log_level: "INFO",
      app_version: "0.1.0",
      schema_revision: "0002_m2_analyst_workflow",
    },
    updated_at: null,
  };
}
