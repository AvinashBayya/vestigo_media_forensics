import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import {
  createCase,
  errorMessage,
  linkArtifactToCase,
  listCases,
  unlinkArtifactFromCase,
} from "../api/client";
import type { CaseInfo, CasesResponse } from "../api/types";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";
const BUTTON = "rounded-md border border-slate-300 px-2 py-1 text-sm font-medium dark:border-slate-600";

/** Put this artifact in a case, or take it out (Pass 3). Organisation, never evidence. */
export function CasesControl({
  artifactId,
  onChanged,
}: {
  artifactId: string;
  onChanged?: () => void;
}) {
  const headingId = useId();
  const [response, setResponse] = useState<CasesResponse | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setResponse(await listCases());
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function member(item: CaseInfo): boolean {
    return item.artifacts.some((artifact) => artifact.artifact_id === artifactId);
  }

  async function act(action: () => Promise<unknown>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      await load();
      onChanged?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    await act(async () => {
      const created = await createCase(trimmed);
      await linkArtifactToCase(created.case_id, artifactId);
      setName("");
    });
  }

  return (
    <section
      aria-labelledby={headingId}
      className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <h2 id={headingId} className="font-medium">
        Cases
      </h2>
      {response && <p className={MUTED}>{response.notice}</p>}

      {error && (
        <p role="alert" className="text-rose-800 dark:text-rose-300">
          {error}
        </p>
      )}

      {response && response.cases.length > 0 && (
        <ul aria-label="Cases" className="space-y-1">
          {response.cases.map((item) => (
            <li key={item.case_id} className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{item.name}</span>
              <span className={MUTED}>
                {item.artifact_count} artifact{item.artifact_count === 1 ? "" : "s"}
              </span>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void act(() =>
                    member(item)
                      ? unlinkArtifactFromCase(item.case_id, artifactId)
                      : linkArtifactToCase(item.case_id, artifactId),
                  )
                }
                className={`${BUTTON} disabled:opacity-40`}
              >
                {member(item) ? "Remove from case" : "Add to case"}
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={(event) => void submit(event)} aria-label="Create a case" className="space-y-1">
        <label className="block space-y-0.5">
          <span className={MUTED}>New case name</span>
          <input
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <button type="submit" disabled={busy || !name.trim()} className={`${BUTTON} disabled:opacity-40`}>
          Create and add this artifact
        </button>
      </form>
    </section>
  );
}
