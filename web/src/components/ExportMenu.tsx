import { useState } from "react";

import { downloadEvidencePackage, errorMessage, evidenceDownloadUrl } from "../api/client";
import { ErrorBanner } from "./Messages";

interface ExportMenuProps {
  artifactId: string;
  /** The analysis shown on the page; exports are of this job. */
  jobId: string;
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** JSON report, or a ZIP evidence package with a SHA-256 manifest (M2-6). */
export function ExportMenu({ artifactId, jobId }: ExportMenuProps) {
  const [includeOriginal, setIncludeOriginal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ filename: string; sha256: string } | null>(null);

  async function downloadPackage() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const result = await downloadEvidencePackage(artifactId, jobId, includeOriginal);
      saveBlob(result.blob, result.filename);
      setDone({ filename: result.filename, sha256: result.sha256 });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Export evidence" className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="font-medium">Export evidence</h2>
      <a
        href={evidenceDownloadUrl(artifactId, jobId)}
        download
        className="block rounded-md border border-slate-300 px-3 py-1.5 text-center font-medium dark:border-slate-700"
      >
        Download JSON report
      </a>
      <div className="space-y-2 rounded-md border border-slate-200 p-2 dark:border-slate-800">
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={includeOriginal}
            onChange={(event) => setIncludeOriginal(event.target.checked)}
            className="mt-0.5"
          />
          <span>Include the original file</span>
        </label>
        <button
          type="button"
          onClick={downloadPackage}
          disabled={busy}
          className="w-full rounded-md bg-slate-900 px-3 py-1.5 font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
        >
          {busy ? "Preparing package…" : "Download evidence package (ZIP)"}
        </button>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Report, review history, raw tool outputs, and a manifest with the SHA-256 of every file.
        </p>
      </div>
      {error && <ErrorBanner message={error} />}
      {done && (
        <div role="status" className="space-y-1 text-xs">
          <p>Downloaded {done.filename}.</p>
          <p>
            Package SHA-256: <span className="font-mono break-all select-all">{done.sha256}</span>
          </p>
          <p className="text-slate-600 dark:text-slate-400">Compare it with the downloaded file to verify it is unchanged.</p>
        </div>
      )}
    </section>
  );
}
