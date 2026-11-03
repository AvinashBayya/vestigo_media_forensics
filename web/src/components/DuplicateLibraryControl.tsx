import { useState } from "react";

import { errorMessage, setDuplicateLibrary } from "../api/client";
import type { ArtifactDetail } from "../api/types";
import { ErrorBanner } from "./Messages";

/** Include or exclude this artifact from future duplicate searches (M2-7). */
export function DuplicateLibraryControl({ artifact, onChanged }: { artifact: ArtifactDetail; onChanged: (a: ArtifactDetail) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const included = artifact.in_duplicate_library;

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      onChanged(await setDuplicateLibrary(artifact.artifact_id, !included));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Duplicate search library" className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="font-medium">Duplicate search library</h2>
      <p>
        {included
          ? "Included: future duplicate searches of other images compare against this one."
          : "Excluded: future duplicate searches of other images skip this one."}
      </p>
      <p className="text-xs text-slate-600 dark:text-slate-400">
        Changing this affects only analyses run afterwards. Evidence already recorded is not changed.
      </p>
      {error && <ErrorBanner message={error} />}
      <button
        type="button"
        onClick={toggle}
        disabled={busy}
        className="rounded-md border border-slate-300 px-3 py-1.5 font-medium disabled:opacity-40 dark:border-slate-700"
      >
        {included ? "Exclude from future searches" : "Include in future searches"}
      </button>
    </section>
  );
}
