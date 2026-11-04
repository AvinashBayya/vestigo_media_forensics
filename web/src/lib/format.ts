import type { EvidenceClassification, JobStatus, ReviewState } from "../api/types";

export const ACTIVE_JOB_STATUSES: JobStatus[] = ["queued", "running"];

export function isActive(status: JobStatus | null | undefined): boolean {
  return status != null && ACTIVE_JOB_STATUSES.includes(status);
}

export const STAGE_LABELS: Record<string, string> = {
  hashes: "File hashes",
  metadata: "Embedded metadata",
  c2pa: "Content Credentials (C2PA)",
  perceptual_hash: "Perceptual hash",
  ocr: "Text in image (OCR)",
  duplicates: "Duplicate search",
  media_info: "Media information",
  scene_changes: "Scene changes",
  keyframes: "Keyframes",
  keyframe_phash: "Keyframe perceptual hashes",
  keyframe_ocr: "Text in keyframes (OCR)",
};

export const REVIEW_LABELS: Record<ReviewState, string> = {
  UNREVIEWED: "Unreviewed",
  IN_REVIEW: "In review",
  REVIEWED: "Reviewed",
  FLAGGED: "Flagged",
  ARCHIVED: "Archived",
};

export const CLASSIFICATION_LABELS: Record<EvidenceClassification, string> = {
  OBSERVED: "Observed — read directly from the file",
  DERIVED: "Derived — calculated by Vestigo",
  EXTERNAL: "External — from an outside service",
  UNVERIFIED: "Unverified",
  REVIEWED: "Reviewed",
};

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}

export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2);
}

export function countTags(groups: Record<string, Record<string, unknown>>): number {
  return Object.values(groups).reduce((total, tags) => total + Object.keys(tags).length, 0);
}

/** Seconds as m:ss (or m:ss.t when there are tenths) for video timestamps and durations. */
export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  const totalTenths = Math.round(seconds * 10);
  const minutes = Math.floor(totalTenths / 600);
  const wholeSeconds = Math.floor((totalTenths - minutes * 600) / 10);
  const tenths = totalTenths % 10;
  const base = `${minutes}:${String(wholeSeconds).padStart(2, "0")}`;
  return tenths > 0 ? `${base}.${tenths}` : base;
}
