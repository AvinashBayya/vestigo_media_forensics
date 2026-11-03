import { useEffect, useId, type ReactNode } from "react";

interface ConfirmDialogProps {
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  tone?: "default" | "danger";
  onCancel: () => void;
  onConfirm: () => void;
}

/** A modal confirmation. Escape and the cancel button (focused first) both cancel. */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  busy = false,
  tone = "default",
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const titleId = useId();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onCancel]);

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md space-y-3 rounded-lg bg-white p-5 text-sm shadow-lg dark:bg-slate-900"
      >
        <h2 id={titleId} className="text-base font-semibold">
          {title}
        </h2>
        {children}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            autoFocus
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-slate-300 px-3 py-1.5 font-medium dark:border-slate-700"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`rounded-md px-3 py-1.5 font-medium text-white disabled:opacity-50 ${
              tone === "danger" ? "bg-rose-700" : "bg-slate-900 dark:bg-slate-100 dark:text-slate-900"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
