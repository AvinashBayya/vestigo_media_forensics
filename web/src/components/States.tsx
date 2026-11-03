import type { ReactNode } from "react";

import { ApiError } from "../api/client";

/** A friendly empty state: what is missing and what the analyst can do about it. */
export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 px-4 py-10 text-center dark:border-slate-700">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-slate-600 dark:text-slate-400">{children}</div>}
      {action && <div className="mt-4 flex justify-center gap-3">{action}</div>}
    </div>
  );
}

/** An error with its code, so it can be reported precisely, and a retry button. */
export function ErrorState({ error, onRetry, title = "This could not be loaded." }: {
  error: ApiError | string;
  onRetry?: () => void;
  title?: string;
}) {
  const message = typeof error === "string" ? error : error.message;
  const code = typeof error === "string" ? null : error.code;
  return (
    <div
      role="alert"
      className="rounded-md border border-rose-300 bg-rose-50 px-3 py-3 text-sm text-rose-900 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-100"
    >
      <p className="font-medium">{title}</p>
      <p className="mt-1">{message}</p>
      <div className="mt-2 flex items-center gap-3">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-rose-400 px-2 py-1 font-medium hover:bg-rose-100 dark:hover:bg-rose-900"
          >
            Retry
          </button>
        )}
        {code && <span className="font-mono text-xs">Error code: {code}</span>}
      </div>
    </div>
  );
}

/** Placeholder rows shown while the first page loads. */
export function TableSkeleton({ rows = 5, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-2">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-9 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
      ))}
    </div>
  );
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.code === "NETWORK_ERROR";
}
