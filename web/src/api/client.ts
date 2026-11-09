import axios, { isAxiosError } from "axios";

import type {
  AnalysisOptions,
  ApiErrorBody,
  ArtifactDetail,
  ArtifactList,
  ArtifactQuery,
  CustodyReport,
  ExternalLead,
  ExternalLeadCreate,
  ExternalLeadsResponse,
  ExternalLeadUpdate,
  LocationCandidate,
  LocationCandidateCreate,
  LocationCandidatesResponse,
  LocationCandidateUpdate,
  AIDraft,
  AIDraftsResponse,
  AIStatus,
  AnswerResponse,
  CaseInfo,
  CasesResponse,
  DocumentAnalysisOptions,
  DraftSource,
  GeoToolsResponse,
  FieldAction,
  IndexResult,
  SemanticSearchResponse,
  Transcript,
  TranscriptsResponse,
  SearchProvidersResponse,
  ArtifactUploadResponse,
  BulkReviewResult,
  DeletionSummary,
  EvidenceReport,
  HealthResponse,
  JobHistory,
  LibrarySummary,
  JobCreated,
  JobStatusResponse,
  MediaType,
  PreviewInfo,
  RecordReview,
  ReviewHistory,
  SettingsResponse,
  EditableSettings,
  VideoAnalysisOptions,
  AudioAnalysisOptions,
  ReviewState,
} from "./types";

export const API_BASE = "/api/v1";

const http = axios.create({ baseURL: API_BASE });

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(code: string, message: string, status: number, details: Record<string, unknown> = {}) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function toApiError(error: unknown): ApiError {
  if (isAxiosError(error)) {
    const body = error.response?.data as { error?: ApiErrorBody } | undefined;
    if (body?.error) {
      return new ApiError(body.error.code, body.error.message, error.response!.status, body.error.details);
    }
    if (!error.response) {
      return new ApiError(
        "NETWORK_ERROR",
        "Could not reach the Vestigo backend. Check that it is running on port 8400.",
        0,
      );
    }
    return new ApiError("HTTP_ERROR", `The backend responded with status ${error.response.status}.`, error.response.status);
  }
  return new ApiError("UNKNOWN_ERROR", error instanceof Error ? error.message : "Something went wrong.", 0);
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : toApiError(error).message;
}

async function call<T>(request: Promise<{ data: T }>): Promise<T> {
  try {
    return (await request).data;
  } catch (error) {
    throw toApiError(error);
  }
}

export const DEFAULT_OPTIONS: AnalysisOptions = {
  metadata: true,
  c2pa: true,
  location_clues: true,
  structural: true,
  forensic_indicators: true,
  ocr: true,
  duplicate_search: true,
};

export function uploadArtifact(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<ArtifactUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return call(
    http.post<ArtifactUploadResponse>("/artifacts/upload", form, {
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded / event.total) * 100));
        }
      },
    }),
  );
}

/** Without `options`, the backend uses the default analysis options from Settings. */
export function startImageAnalysis(artifactId: string, options?: AnalysisOptions): Promise<JobCreated> {
  return call(
    http.post<JobCreated>("/analysis/image", { artifact_id: artifactId, ...(options ? { options } : {}) }),
  );
}

/** Without `options`, the backend uses the saved default video analysis options. */
export function startVideoAnalysis(artifactId: string, options?: VideoAnalysisOptions): Promise<JobCreated> {
  return call(
    http.post<JobCreated>("/analysis/video", { artifact_id: artifactId, ...(options ? { options } : {}) }),
  );
}

/** Without `options`, the backend uses the saved default audio analysis options. */
export function startAudioAnalysis(artifactId: string, options?: AudioAnalysisOptions): Promise<JobCreated> {
  return call(
    http.post<JobCreated>("/analysis/audio", { artifact_id: artifactId, ...(options ? { options } : {}) }),
  );
}

/** Starts the pipeline matching the artifact's media type, with the saved defaults. */
export function startDocumentAnalysis(
  artifactId: string,
  options?: DocumentAnalysisOptions,
): Promise<JobCreated> {
  return call(
    http.post<JobCreated>("/analysis/document", { artifact_id: artifactId, ...(options ? { options } : {}) }),
  );
}

export function startAnalysis(artifactId: string, mediaType: MediaType): Promise<JobCreated> {
  if (mediaType === "video") return startVideoAnalysis(artifactId);
  if (mediaType === "audio") return startAudioAnalysis(artifactId);
  if (mediaType === "document") return startDocumentAnalysis(artifactId);
  return startImageAnalysis(artifactId);
}

/** A derived file's content (for example a keyframe thumbnail). */
export function derivedContentUrl(artifactId: string, derivedFileId: string): string {
  return `${API_BASE}/artifacts/${encodeURIComponent(artifactId)}/derived/${encodeURIComponent(derivedFileId)}/content`;
}

export function getJob(jobId: string): Promise<JobStatusResponse> {
  return call(http.get<JobStatusResponse>(`/analysis/jobs/${encodeURIComponent(jobId)}`));
}

/** Repeated keys for lists (`review_state=A&review_state=B`), as FastAPI expects. */
export function toSearchParams(query: ArtifactQuery): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    for (const item of Array.isArray(value) ? value : [value]) params.append(key, String(item));
  }
  return params;
}

export function listArtifacts(query: ArtifactQuery = {}): Promise<ArtifactList> {
  return call(http.get<ArtifactList>("/artifacts", { params: toSearchParams(query) }));
}

export function getArtifact(artifactId: string): Promise<ArtifactDetail> {
  return call(http.get<ArtifactDetail>(`/artifacts/${encodeURIComponent(artifactId)}`));
}

export function getEvidence(artifactId: string, jobId?: string): Promise<EvidenceReport> {
  return call(
    http.get<EvidenceReport>(`/artifacts/${encodeURIComponent(artifactId)}/evidence`, {
      params: jobId ? { job_id: jobId } : undefined,
    }),
  );
}

/**
 * Saves the artifact's review. `expectedUpdatedAt` is the review timestamp the analyst last saw; the
 * backend refuses the save with REVIEW_CONFLICT if the review has changed since.
 */
export function updateReview(
  artifactId: string,
  state: ReviewState,
  analystNotes: string,
  expectedUpdatedAt?: string,
): Promise<ArtifactDetail> {
  return call(
    http.patch<ArtifactDetail>(`/artifacts/${encodeURIComponent(artifactId)}/review`, {
      state,
      analyst_notes: analystNotes,
      ...(expectedUpdatedAt !== undefined ? { expected_updated_at: expectedUpdatedAt } : {}),
    }),
  );
}

export function updateRecordReview(
  artifactId: string,
  evidenceId: string,
  state: ReviewState,
  analystNotes: string,
  expectedUpdatedAt: string | null,
): Promise<RecordReview> {
  return call(
    http.patch<RecordReview>(
      `/artifacts/${encodeURIComponent(artifactId)}/evidence/${encodeURIComponent(evidenceId)}/review`,
      { state, analyst_notes: analystNotes, expected_updated_at: expectedUpdatedAt },
    ),
  );
}

export function bulkReview(artifactIds: string[], state: ReviewState): Promise<BulkReviewResult> {
  return call(http.post<BulkReviewResult>("/artifacts/review", { artifact_ids: artifactIds, state }));
}

export function getReviewHistory(artifactId: string): Promise<ReviewHistory> {
  return call(http.get<ReviewHistory>(`/artifacts/${encodeURIComponent(artifactId)}/review-history`));
}

export function deleteArtifact(artifactId: string): Promise<DeletionSummary> {
  return call(http.delete<DeletionSummary>(`/artifacts/${encodeURIComponent(artifactId)}`));
}

export function contentUrl(artifactId: string): string {
  return `${API_BASE}/artifacts/${encodeURIComponent(artifactId)}/content`;
}

export function evidenceDownloadUrl(artifactId: string, jobId: string): string {
  const params = new URLSearchParams({ job_id: jobId, download: "true" });
  return `${API_BASE}/artifacts/${encodeURIComponent(artifactId)}/evidence?${params}`;
}

export function getJobHistory(artifactId: string): Promise<JobHistory> {
  return call(http.get<JobHistory>(`/artifacts/${encodeURIComponent(artifactId)}/jobs`));
}

/** Health is reported with HTTP 503 when the database or storage fails; the body is still a report. */
export async function getHealth(): Promise<HealthResponse> {
  try {
    return (await http.get<HealthResponse>("/health", { validateStatus: (status) => status === 200 || status === 503 }))
      .data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Includes or excludes the artifact from future duplicate searches. Recorded evidence is not changed. */
export function setDuplicateLibrary(artifactId: string, included: boolean): Promise<ArtifactDetail> {
  return call(http.patch<ArtifactDetail>(`/artifacts/${encodeURIComponent(artifactId)}/duplicate-library`, { included }));
}

export function getLibrarySummary(): Promise<LibrarySummary> {
  return call(http.get<LibrarySummary>("/library/summary"));
}

export interface DownloadedPackage {
  blob: Blob;
  filename: string;
  /** SHA-256 of the whole ZIP, from the X-Vestigo-Export-SHA256 header. */
  sha256: string;
}

/** Downloads the ZIP evidence package (M2-6) for one job. The original is included only on request. */
export async function downloadEvidencePackage(
  artifactId: string,
  jobId: string,
  includeOriginal: boolean,
): Promise<DownloadedPackage> {
  try {
    const response = await http.get<Blob>(`/artifacts/${encodeURIComponent(artifactId)}/export`, {
      params: { job_id: jobId, include_original: includeOriginal },
      responseType: "blob",
    });
    const disposition = String(response.headers["content-disposition"] ?? "");
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `vestigo-evidence-${artifactId}-${jobId}.zip`;
    return { blob: response.data, filename, sha256: String(response.headers["x-vestigo-export-sha256"] ?? "") };
  } catch (error) {
    // Error bodies arrive as a Blob when a blob response was requested.
    if (isAxiosError(error) && error.response?.data instanceof Blob) {
      try {
        error.response.data = JSON.parse(await error.response.data.text());
      } catch {
        // Not JSON; fall through to the generic message.
      }
    }
    throw toApiError(error);
  }
}

export function getSettings(): Promise<SettingsResponse> {
  return call(http.get<SettingsResponse>("/settings"));
}

export function updateSettings(changes: Partial<EditableSettings>): Promise<SettingsResponse> {
  return call(http.patch<SettingsResponse>("/settings", changes));
}

/** Creates (or returns) the re-encoded viewing copy of a video the browser cannot play (D19). */
export function createPlayablePreview(artifactId: string): Promise<PreviewInfo> {
  return call(http.post<PreviewInfo>(`/artifacts/${encodeURIComponent(artifactId)}/preview`));
}

export function previewContentUrl(artifactId: string): string {
  return `${API_BASE}/artifacts/${encodeURIComponent(artifactId)}/preview/content`;
}

export function getCustody(artifactId: string): Promise<CustodyReport> {
  return call(http.get<CustodyReport>(`/artifacts/${encodeURIComponent(artifactId)}/custody`));
}

export function getSearchProviders(): Promise<SearchProvidersResponse> {
  return call(http.get<SearchProvidersResponse>("/search/providers"));
}

export function listExternalLeads(artifactId: string): Promise<ExternalLeadsResponse> {
  return call(http.get<ExternalLeadsResponse>(`/artifacts/${encodeURIComponent(artifactId)}/external-leads`));
}

export function createExternalLead(artifactId: string, lead: ExternalLeadCreate): Promise<ExternalLead> {
  return call(http.post<ExternalLead>(`/artifacts/${encodeURIComponent(artifactId)}/external-leads`, lead));
}

export function updateExternalLead(
  artifactId: string,
  leadId: string,
  update: ExternalLeadUpdate,
): Promise<ExternalLead> {
  return call(
    http.patch<ExternalLead>(
      `/artifacts/${encodeURIComponent(artifactId)}/external-leads/${encodeURIComponent(leadId)}`,
      update,
    ),
  );
}

export function deleteExternalLead(artifactId: string, leadId: string): Promise<void> {
  return call(
    http.delete<void>(
      `/artifacts/${encodeURIComponent(artifactId)}/external-leads/${encodeURIComponent(leadId)}`,
    ),
  );
}

/** The original or a derived file as an attachment, for manual upload to a search provider (M5). */
export function downloadUrl(artifactId: string, derivedFileId?: string | null): string {
  const base = derivedFileId ? derivedContentUrl(artifactId, derivedFileId) : contentUrl(artifactId);
  return `${base}?download=true`;
}

export function listLocationCandidates(artifactId: string): Promise<LocationCandidatesResponse> {
  return call(
    http.get<LocationCandidatesResponse>(
      `/artifacts/${encodeURIComponent(artifactId)}/location-candidates`,
    ),
  );
}

export function createLocationCandidate(
  artifactId: string,
  candidate: LocationCandidateCreate,
): Promise<LocationCandidate> {
  return call(
    http.post<LocationCandidate>(
      `/artifacts/${encodeURIComponent(artifactId)}/location-candidates`,
      candidate,
    ),
  );
}

export function updateLocationCandidate(
  artifactId: string,
  candidateId: string,
  update: LocationCandidateUpdate,
): Promise<LocationCandidate> {
  return call(
    http.patch<LocationCandidate>(
      `/artifacts/${encodeURIComponent(artifactId)}/location-candidates/${encodeURIComponent(candidateId)}`,
      update,
    ),
  );
}

export function deleteLocationCandidate(artifactId: string, candidateId: string): Promise<void> {
  return call(
    http.delete<void>(
      `/artifacts/${encodeURIComponent(artifactId)}/location-candidates/${encodeURIComponent(candidateId)}`,
    ),
  );
}

/**
 * An OpenStreetMap link for coordinates, built entirely in the browser (M6): the backend never
 * constructs, stores, or logs a coordinate-bearing URL. Opening it sends the coordinates to
 * openstreetmap.org, which is why the UI warns before the analyst clicks.
 */
export function openStreetMapUrl(latitude: number, longitude: number): string {
  const params = new URLSearchParams({
    mlat: String(latitude),
    mlon: String(longitude),
  });
  return `https://www.openstreetmap.org/?${params.toString()}#map=15/${latitude}/${longitude}`;
}

// --- Local AI (Pass 1) ---------------------------------------------------------------------------

export function getAIStatus(): Promise<AIStatus> {
  return call(http.get<AIStatus>("/ai/status"));
}

export function listAIDrafts(artifactId: string): Promise<AIDraftsResponse> {
  return call(http.get<AIDraftsResponse>(`/ai/artifacts/${encodeURIComponent(artifactId)}/drafts`));
}

export function createAIDraft(
  artifactId: string,
  request: { source_kind: DraftSource; fields: string[] },
): Promise<AIDraft> {
  return call(http.post<AIDraft>(`/ai/artifacts/${encodeURIComponent(artifactId)}/drafts`, request));
}

export function decideDraftField(
  artifactId: string,
  draftId: string,
  decision: { field: string; action: FieldAction; value?: string },
): Promise<AIDraft> {
  return call(
    http.patch<AIDraft>(
      `/ai/artifacts/${encodeURIComponent(artifactId)}/drafts/${encodeURIComponent(draftId)}`,
      decision,
    ),
  );
}

export function deleteAIDraft(artifactId: string, draftId: string): Promise<void> {
  return call(
    http.delete<void>(
      `/ai/artifacts/${encodeURIComponent(artifactId)}/drafts/${encodeURIComponent(draftId)}`,
    ),
  );
}

export function listTranscripts(artifactId: string): Promise<TranscriptsResponse> {
  return call(
    http.get<TranscriptsResponse>(`/ai/artifacts/${encodeURIComponent(artifactId)}/transcripts`),
  );
}

export function createTranscript(artifactId: string, language?: string): Promise<Transcript> {
  return call(
    http.post<Transcript>(`/ai/artifacts/${encodeURIComponent(artifactId)}/transcripts`, {
      ...(language ? { language } : {}),
    }),
  );
}

export function updateTranscript(
  artifactId: string,
  transcriptId: string,
  update: { edited_text?: string; review_state?: ReviewState },
): Promise<Transcript> {
  return call(
    http.patch<Transcript>(
      `/ai/artifacts/${encodeURIComponent(artifactId)}/transcripts/${encodeURIComponent(transcriptId)}`,
      update,
    ),
  );
}

export function deleteTranscript(artifactId: string, transcriptId: string): Promise<void> {
  return call(
    http.delete<void>(
      `/ai/artifacts/${encodeURIComponent(artifactId)}/transcripts/${encodeURIComponent(transcriptId)}`,
    ),
  );
}

export function indexArtifact(artifactId: string): Promise<IndexResult> {
  return call(http.post<IndexResult>(`/ai/artifacts/${encodeURIComponent(artifactId)}/index`));
}

export function clearArtifactIndex(artifactId: string): Promise<IndexResult> {
  return call(http.delete<IndexResult>(`/ai/artifacts/${encodeURIComponent(artifactId)}/index`));
}

export function semanticSearch(query: string, limit = 20): Promise<SemanticSearchResponse> {
  return call(http.get<SemanticSearchResponse>("/ai/search", { params: { q: query, limit } }));
}

export function askQuestion(question: string, artifactIds?: string[]): Promise<AnswerResponse> {
  return call(
    http.post<AnswerResponse>("/ai/answer", {
      question,
      ...(artifactIds && artifactIds.length > 0 ? { artifact_ids: artifactIds } : {}),
    }),
  );
}

// --- Cases and geospatial tools (Pass 3) ---------------------------------------------------------

export function listCases(): Promise<CasesResponse> {
  return call(http.get<CasesResponse>("/cases"));
}

export function createCase(name: string, notes = ""): Promise<CaseInfo> {
  return call(http.post<CaseInfo>("/cases", { name, notes }));
}

export function deleteCase(caseId: string): Promise<void> {
  return call(http.delete<void>(`/cases/${encodeURIComponent(caseId)}`));
}

export function linkArtifactToCase(caseId: string, artifactId: string): Promise<CaseInfo> {
  return call(
    http.put<CaseInfo>(
      `/cases/${encodeURIComponent(caseId)}/artifacts/${encodeURIComponent(artifactId)}`,
    ),
  );
}

export function unlinkArtifactFromCase(caseId: string, artifactId: string): Promise<CaseInfo> {
  return call(
    http.delete<CaseInfo>(
      `/cases/${encodeURIComponent(caseId)}/artifacts/${encodeURIComponent(artifactId)}`,
    ),
  );
}

export function getGeoTools(artifactId: string): Promise<GeoToolsResponse> {
  return call(http.get<GeoToolsResponse>(`/geo/artifacts/${encodeURIComponent(artifactId)}/tools`));
}
