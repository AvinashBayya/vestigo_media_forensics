import type {
  ArtifactDetail,
  ArtifactList,
  ArtifactListItem,
  C2PASection,
  CustodyReport,
  ExternalLead,
  HealthResponse,
  JobHistoryItem,
  SearchProvidersResponse,
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
    duration_seconds: null,
    review_state: "UNREVIEWED",
    latest_job_status: "completed",
    sha256: "a".repeat(64),
    md5: "b".repeat(32),
    width: 640,
    height: 480,
    has_playable_preview: false,
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
    duration_seconds: null,
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

export const VALIDATOR = "c2pa-python 0.38.1 (c2pa-rs 0.91.3)";

/** A validated C2PA section (M4). Defaults to the usual case: no C2PA data in the file. */
export function c2paSection(overrides: Partial<C2PASection> = {}): C2PASection {
  return {
    present: false,
    validation_performed: true,
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
    status: "absent",
    validation_state: null,
    manifest_count: 0,
    active_manifest: null,
    manifests: [],
    validation_codes: { success: [], informational: [], failure: [] },
    validator: VALIDATOR,
    validator_error: null,
    provenance: provenance("c2pa", { classification: "OBSERVED" }),
    ...overrides,
  };
}

export function evidenceReport(overrides: Partial<EvidenceReport> = {}): EvidenceReport {
  return {
    schema_version: "1.2",
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
    c2pa: c2paSection(),
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
          media_type: "image",
          similarity: 1,
          distance: 0,
          match_type: "exact_file",
          matched_frame_count: null,
          frame_matches: null,
        },
      ],
      provenance: provenance("duplicates"),
    },
    media_info: null,
    scene_changes: null,
    keyframes: null,
    keyframe_phash: null,
    keyframe_ocr: null,
    review: { state: "UNREVIEWED", analyst_notes: "", updated_at: NOW },
    review_history: [],
    external_leads: [],
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
      default_video_analysis_options: {
        metadata: true,
        c2pa: true,
        scene_detection: true,
        keyframe_ocr: false,
        duplicate_search: true,
      },
      default_audio_analysis_options: { metadata: true, c2pa: true, duplicate_search: true },
      library_page_size: 25,
      auto_analyze_after_upload: true,
      enabled_search_providers: [],
      ...editable,
    },
    environment: {
      data_dir: "/workspaces/vestigo-media-forensics/data",
      max_upload_bytes: 52_428_800,
      max_image_pixels: 100_000_000,
      duplicate_threshold: 10,
      max_video_upload_bytes: 524_288_000,
      max_video_duration_seconds: 900,
      max_video_pixels: 8_294_400,
      max_keyframes: 40,
      scene_threshold: 0.3,
      video_timeout_seconds: 600,
      max_audio_upload_bytes: 209_715_200,
      max_audio_duration_seconds: 7200,
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

export const DERIVED_KF_1 = "df_" + "1".repeat(32);
export const DERIVED_KF_2 = "df_" + "2".repeat(32);

/** An analysed video artifact with every video section filled. */
export function videoDetail(overrides: Partial<ArtifactDetail> = {}): ArtifactDetail {
  return artifactDetail({
    filename: "scenes.mp4",
    media_type: "video",
    mime_type: "video/mp4",
    size_bytes: 388_000,
    width: 640,
    height: 360,
    duration_seconds: 9.0,
    ...overrides,
  });
}

export function videoReport(overrides: Partial<EvidenceReport> = {}): EvidenceReport {
  const base = evidenceReport({
    c2pa: c2paSection({ details: {} }),
    perceptual_hash: null,
    ocr: null,
    media_info: {
      container: {
        format_name: "mov,mp4,m4a,3gp,3g2,mj2",
        format_long_name: "QuickTime / MOV",
        duration_seconds: 9.0,
        size_bytes: 388_000,
        bit_rate: 344_000,
        stream_count: 2,
      },
      video_streams: [
        {
          index: 0,
          codec: "h264",
          profile: "High",
          width: 640,
          height: 360,
          frame_rate: 25,
          bit_rate: 240_000,
          pixel_format: "yuv420p",
          rotation: null,
        },
      ],
      audio_streams: [
        {
          index: 1,
          codec: "aac",
          profile: "LC",
          channels: 1,
          channel_layout: "mono",
          sample_rate: 44_100,
          bit_rate: 69_000,
        },
      ],
      other_streams: [],
      provenance: provenance("media_info", { classification: "OBSERVED", tool: "ffprobe", tool_version: "7.1.5" }),
    },
    scene_changes: {
      threshold: 0.3,
      count: 2,
      changes: [
        { time: 3.023, score: 0.5788 },
        { time: 6.023, score: 0.8158 },
      ],
      provenance: provenance("scene_changes", { tool: "ffmpeg", tool_version: "7.1.5" }),
    },
    keyframes: {
      policy: { min_keyframes: 8, max_keyframes: 40, dedupe_seconds: 0.25, thumbnail_max_side: 1920 },
      requested: 8,
      extracted: 8,
      frames: [
        { seq: 1, timestamp: 0, reason: "first_frame", scene_score: null, derived_file_id: DERIVED_KF_1, width: 640, height: 360 },
        { seq: 2, timestamp: 3.023, reason: "scene_change", scene_score: 0.5788, derived_file_id: DERIVED_KF_2, width: 640, height: 360 },
      ],
      provenance: provenance("keyframes", { tool: "ffmpeg", tool_version: "7.1.5" }),
    },
    keyframe_phash: {
      algorithm: "pHash",
      bits: 64,
      count: 2,
      frames: [
        { seq: 1, timestamp: 0, value: "c4c4c4c43b3b3b3b", derived_file_id: DERIVED_KF_1 },
        { seq: 2, timestamp: 3.023, value: "8469a2964f8f9b17", derived_file_id: DERIVED_KF_2 },
      ],
      provenance: provenance("keyframe_phash", { tool: "imagehash", tool_version: "4.3.2" }),
    },
    keyframe_ocr: {
      engine: "tesseract",
      languages: ["eng"],
      frame_limit: 10,
      analyzed: 2,
      frames: [
        {
          seq: 1,
          timestamp: 0,
          text: "SCENE ONE",
          cleaned_text: null,
          cleaning: [],
          confidence: 0.96,
          word_count: 2,
          preprocessing: [],
          candidates: [],
          selected: { variant: "grayscale", reason: "The threshold pass was not used." },
        },
        {
          seq: 2,
          timestamp: 3.023,
          text: "",
          cleaned_text: null,
          cleaning: [],
          confidence: null,
          word_count: 0,
          preprocessing: [],
          candidates: [],
          selected: { variant: "grayscale", reason: "Neither pass found words with enough confidence." },
        },
      ],
      provenance: provenance("keyframe_ocr", { tool: "Tesseract", tool_version: "5.5.0; Pillow 13.0.0" }),
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
          filename: "recoded.webm",
          available: true,
          media_type: "video",
          similarity: 0.9688,
          distance: 2,
          match_type: "near",
          matched_frame_count: 2,
          frame_matches: [
            {
              distance: 0,
              similarity: 1,
              query_seq: 1,
              query_timestamp: 0,
              matched_seq: 1,
              matched_timestamp: 0,
              rotation_degrees: 0,
              mirrored: false,
            },
            {
              distance: 2,
              similarity: 0.9688,
              query_seq: 2,
              query_timestamp: 3.023,
              matched_seq: 2,
              matched_timestamp: 3.1,
              rotation_degrees: 270,
              mirrored: false,
            },
          ],
        },
      ],
      provenance: provenance("duplicates"),
    },
  });
  return { ...base, ...overrides };
}

/** A custody report for an uploaded-and-analysed image (M4B). */
export function custodyReport(overrides: Partial<CustodyReport> = {}): CustodyReport {
  return {
    artifact_id: ARTIFACT_ID,
    notice:
      "This chain of custody lists what Vestigo recorded on this machine since the file was " +
      "uploaded. It is not a legal chain of custody, it says nothing about the file's history " +
      "before upload, and no event is ever inferred: evidence-package exports and duplicate-library " +
      "changes made before schema revision 0005 were not recorded anywhere and therefore do not " +
      "appear. Derived files written before that revision have no recorded source.",
    events: [
      {
        type: "uploaded",
        at: "2026-11-02T08:59:00.000000Z",
        source_table: "artifacts",
        detail: {
          filename: "harbour.jpg",
          media_type: "image",
          mime_type: "image/jpeg",
          size_bytes: 36_000,
          sha256: "a".repeat(64),
        },
      },
      {
        type: "analysis_started",
        at: NOW,
        source_table: "analysis_jobs",
        detail: { job_id: JOB_ID, pipeline: "image.v1", app_version: "0.1.0" },
      },
      {
        type: "analysis_finished",
        at: "2026-11-02T09:00:20.000000Z",
        source_table: "analysis_jobs",
        detail: {
          job_id: JOB_ID,
          pipeline: "image.v1",
          app_version: "0.1.0",
          status: "completed",
          evidence_records: 6,
          derived_files: 2,
        },
      },
    ],
    derived_files: [
      {
        derived_file_id: "df_" + "7".repeat(32),
        job_id: JOB_ID,
        stage: "metadata",
        kind: "exiftool_json",
        filename: "metadata.exiftool.json",
        sha256: "c".repeat(64),
        size_bytes: 2048,
        created_at: NOW,
        source_kind: "original",
        source_derived_file_id: null,
      },
      {
        derived_file_id: "df_" + "8".repeat(32),
        job_id: JOB_ID,
        stage: "keyframe_ocr",
        kind: "tesseract_tsv_grayscale",
        filename: "keyframe_ocr.0001.grayscale.tsv",
        sha256: "d".repeat(64),
        size_bytes: 512,
        created_at: NOW,
        source_kind: "derived_file",
        source_derived_file_id: "df_" + "7".repeat(32),
      },
    ],
    ...overrides,
  };
}

/** The provider registry as served, with nothing enabled (M5 default). */
export function searchProviders(enabled: string[] = []): SearchProvidersResponse {
  const providers = [
    { key: "google_lens", name: "Google Lens", landing_url: "https://lens.google.com/", terms_url: "https://policies.google.com/terms", instructions: "Drag the downloaded image in." },
    { key: "bing_visual", name: "Bing Visual Search", landing_url: "https://www.bing.com/visualsearch", terms_url: "https://www.microsoft.com/servicesagreement", instructions: "Drag the downloaded image into the search box." },
    { key: "tineye", name: "TinEye", landing_url: "https://tineye.com/", terms_url: "https://tineye.com/terms", instructions: "Click the upload arrow and choose the downloaded image." },
    { key: "yandex_images", name: "Yandex Images", landing_url: "https://yandex.com/images/", terms_url: "https://yandex.com/legal/rules/", instructions: "Click the camera icon and upload the downloaded image." },
  ];
  return {
    notice:
      "Opening a provider page sends nothing: it is the provider's plain landing page with no " +
      "information about your evidence. If you then upload the image there yourself, you are " +
      "sharing that media with the external service under its own terms, outside Vestigo's control.",
    providers: providers.map((provider) => ({ ...provider, enabled: enabled.includes(provider.key) })),
  };
}

export const LEADS_NOTICE =
  "External leads are analyst statements: the result URL, image URL, and any publication date are " +
  "recorded exactly as the analyst entered them and are not verified by Vestigo. 'Recorded' is when " +
  "the lead was saved here; a publication date is analyst-reported and unverified. An earlier-dated " +
  "result is a lead about prior appearance, never proof of the original source.";

export function externalLead(overrides: Partial<ExternalLead> = {}): ExternalLead {
  return {
    lead_id: "lead_" + "1".repeat(32),
    artifact_id: ARTIFACT_ID,
    derived_file_id: null,
    provider: "TinEye",
    result_url: "https://example.org/results/42",
    image_url: null,
    claimed_published_at: null,
    notes: "",
    classification: "EXTERNAL",
    review_state: "UNREVIEWED",
    recorded_at: NOW,
    updated_at: null,
    ...overrides,
  };
}
