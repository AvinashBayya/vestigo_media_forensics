import type { ReactNode } from "react";

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-900 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-100"
    >
      {message}
    </div>
  );
}

export function InfoBanner({ children }: { children: ReactNode }) {
  return (
    <div
      role="status"
      className="rounded-md border border-sky-300 bg-sky-50 px-3 py-2 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-100"
    >
      {children}
    </div>
  );
}

export const DEFAULT_NOTICE =
  "Vestigo lists signals observed in the file and derived from it, with the method and limitations " +
  "of each. It does not determine whether media is authentic, manipulated, or truthful. Conclusions " +
  "are for you, the analyst, to draw.";

export function EvidenceNotice({ text = DEFAULT_NOTICE }: { text?: string }) {
  return (
    <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
      {text}
    </p>
  );
}
