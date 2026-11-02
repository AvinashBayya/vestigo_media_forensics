import { useEffect, useId } from "react";

interface DeleteArtifactDialogProps {
  filename: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function DeleteArtifactDialog({ filename, busy, onCancel, onConfirm }: DeleteArtifactDialogProps) {
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
          Delete “{filename}”?
        </h2>
        <p>This permanently deletes:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>the original file</li>
          <li>derived files (raw tool output)</li>
          <li>all analysis jobs and evidence records</li>
          <li>its database records</li>
        </ul>
        <p className="font-medium">This cannot be undone.</p>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            autoFocus
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-slate-300 px-3 py-1.5 font-medium dark:border-slate-700"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-md bg-rose-700 px-3 py-1.5 font-medium text-white disabled:opacity-50"
          >
            {busy ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}
