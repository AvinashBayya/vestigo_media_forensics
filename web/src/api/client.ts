import axios, { isAxiosError } from "axios";

import type {
  AnalysisOptions,
  ApiErrorBody,
  ArtifactDetail,
  ArtifactList,
  ArtifactQuery,
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
export function startAnalysis(artifactId: string, mediaType: MediaType): Promise<JobCreated> {
  if (mediaType === "video") return startVideoAnalysis(artifactId);
  if (mediaType === "audio") return startAudioAnalysis(artifactId);
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
