import type { AnalysisStatusFilter, ArtifactQuery, ArtifactSort, ReviewState, SortOrder, SupportedMimeType } from "../api/types";
import { REVIEW_STATES } from "../api/types";

/** Library state kept in the URL, so links, reloads, and the back button keep the analyst's view. */
export interface LibraryState {
  q: string;
  review: ReviewState[];
  status: StatusChoice;
  problems: boolean;
  duplicates: boolean;
  type: SupportedMimeType | "";
  from: string; // yyyy-mm-dd, local
  to: string; // yyyy-mm-dd, local, inclusive
  archived: boolean;
  sort: ArtifactSort;
  order: SortOrder;
  page: number; // 1-based
}

export type StatusChoice = "" | "not_analysed" | "in_progress" | "completed" | "completed_with_errors" | "failed";

export const STATUS_CHOICES: { value: StatusChoice; label: string }[] = [
  { value: "", label: "Any analysis status" },
  { value: "not_analysed", label: "Not analysed" },
  { value: "in_progress", label: "Queued or running" },
  { value: "completed", label: "Completed" },
  { value: "completed_with_errors", label: "Completed with errors" },
  { value: "failed", label: "Failed" },
];

export const TYPE_CHOICES: { value: SupportedMimeType | ""; label: string }[] = [
  { value: "", label: "Any file type" },
  { value: "image/jpeg", label: "JPEG" },
  { value: "image/png", label: "PNG" },
  { value: "image/webp", label: "WebP" },
  { value: "image/tiff", label: "TIFF" },
  { value: "video/mp4", label: "MP4 video" },
  { value: "video/quicktime", label: "MOV video" },
  { value: "video/webm", label: "WebM video" },
  { value: "video/x-matroska", label: "MKV video" },
  { value: "video/x-msvideo", label: "AVI video" },
  { value: "video/mp2t", label: "MPEG-TS video" },
  { value: "video/x-ms-wmv", label: "WMV video" },
  { value: "video/x-flv", label: "FLV video" },
  { value: "video/3gpp", label: "3GP video" },
  { value: "video/x-m4v", label: "M4V video" },
];

const SORTS: ArtifactSort[] = ["created_at", "filename", "size_bytes", "review_state"];
const STATUS_FILTERS: Record<Exclude<StatusChoice, "">, AnalysisStatusFilter[]> = {
  not_analysed: ["not_analysed"],
  in_progress: ["queued", "running"],
  completed: ["completed"],
  completed_with_errors: ["completed_with_errors"],
  failed: ["failed"],
};
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export const DEFAULT_STATE: LibraryState = {
  q: "",
  review: [],
  status: "",
  problems: false,
  duplicates: false,
  type: "",
  from: "",
  to: "",
  archived: false,
  sort: "created_at",
  order: "desc",
  page: 1,
};

/** Reads the state from URL parameters, ignoring anything invalid. */
export function parseLibraryState(params: URLSearchParams): LibraryState {
  const sort = params.get("sort") as ArtifactSort;
  const status = params.get("status") as StatusChoice;
  const type = params.get("type") as SupportedMimeType;
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  return {
    q: params.get("q") ?? "",
    review: params.getAll("review").filter((value): value is ReviewState => REVIEW_STATES.includes(value as ReviewState)),
    status: STATUS_CHOICES.some((choice) => choice.value === status) ? status : "",
    problems: params.get("problems") === "1",
    duplicates: params.get("duplicates") === "1",
    type: TYPE_CHOICES.some((choice) => choice.value === type) ? type : "",
    from: DATE.test(params.get("from") ?? "") ? params.get("from")! : "",
    to: DATE.test(params.get("to") ?? "") ? params.get("to")! : "",
    archived: params.get("archived") === "1",
    sort: SORTS.includes(sort) ? sort : "created_at",
    order: params.get("order") === "asc" ? "asc" : "desc",
    page: Number.isFinite(page) && page >= 1 ? page : 1,
  };
}

/** Writes only non-default values, so URLs stay short. */
export function toUrlParams(state: LibraryState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  for (const value of state.review) params.append("review", value);
  if (state.status) params.set("status", state.status);
  if (state.problems) params.set("problems", "1");
  if (state.duplicates) params.set("duplicates", "1");
  if (state.type) params.set("type", state.type);
  if (state.from) params.set("from", state.from);
  if (state.to) params.set("to", state.to);
  if (state.archived) params.set("archived", "1");
  if (state.sort !== DEFAULT_STATE.sort) params.set("sort", state.sort);
  if (state.order !== DEFAULT_STATE.order) params.set("order", state.order);
  if (state.page > 1) params.set("page", String(state.page));
  return params;
}

function localDayStart(day: string): string {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(year, month - 1, date, 0, 0, 0, 0).toISOString();
}

function localDayEnd(day: string): string {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(year, month - 1, date, 23, 59, 59, 999).toISOString();
}

export function toArtifactQuery(state: LibraryState, pageSize: number): ArtifactQuery {
  return {
    q: state.q.trim() || undefined,
    review_state: state.review.length ? state.review : undefined,
    analysis_status: state.status ? STATUS_FILTERS[state.status] : undefined,
    has_problems: state.problems || undefined,
    has_duplicates: state.duplicates || undefined,
    mime_type: state.type ? [state.type] : undefined,
    uploaded_from: state.from ? localDayStart(state.from) : undefined,
    uploaded_to: state.to ? localDayEnd(state.to) : undefined,
    include_archived: state.archived,
    sort: state.sort,
    order: state.order,
    limit: pageSize,
    offset: (state.page - 1) * pageSize,
  };
}

/** True when anything narrows the results (search or a filter), as opposed to sort or page. */
export function isFiltered(state: LibraryState): boolean {
  return Boolean(
    state.q.trim() ||
      state.review.length ||
      state.status ||
      state.problems ||
      state.duplicates ||
      state.type ||
      state.from ||
      state.to ||
      state.archived,
  );
}

export function clearFilters(state: LibraryState): LibraryState {
  return { ...DEFAULT_STATE, sort: state.sort, order: state.order };
}
