import { useId, useState, type ChangeEvent } from "react";

import { deleteAIModel, errorMessage, getAIModels, getAIStatus, importAIModel } from "../api/client";
import { useApiResource } from "../lib/useApiResource";
import type { EditableSettings, ManagedModelInfo } from "../api/types";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";
const BUTTON = "rounded-md border border-slate-300 px-2 py-1 text-sm font-medium dark:border-slate-600";
const INPUT =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900";

/** "the model the engine carries" - an empty path is a valid, documented choice, not a blank. */
const ENGINE_DEFAULT = "";

function megabytes(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(2)} MB`;
}

/**
 * Choosing, staging and removing local AI model files (D27).
 *
 * Nothing here downloads anything. The analyst picks a staged file or types a path, and the list is
 * a plain scan of the models directory, so dropping a file in by hand works exactly as well.
 */
export function AIModelSettings({
  form,
  onChange,
}: {
  form: EditableSettings;
  onChange: (next: EditableSettings) => void;
}) {
  const draftsId = useId();
  const speechId = useId();
  const models = useApiResource(getAIModels, "ai-models");
  const status = useApiResource(getAIStatus, "ai-models-status");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const staged = models.data?.models ?? [];

  async function act(action: () => Promise<unknown>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      models.reload();
      status.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void act(() => importAIModel(file));
  }

  function picker(id: string, label: string, key: "ai_model_path" | "transcription_model_path") {
    const value = form[key] ?? "";
    const known = value === ENGINE_DEFAULT || staged.some((model) => model.path === value);
    return (
      <div className="space-y-1">
        <label className="block space-y-0.5" htmlFor={id}>
          <span className={MUTED}>{label}</span>
          <select
            id={id}
            className={INPUT}
            value={known ? value : "custom"}
            onChange={(event) => {
              const next = event.target.value;
              if (next !== "custom") onChange({ ...form, [key]: next });
            }}
          >
            <option value={ENGINE_DEFAULT}>Use the model the engine carries</option>
            {staged.map((model) => (
              <option key={model.path} value={model.path}>
                {model.name} ({megabytes(model.size_bytes)})
              </option>
            ))}
            {!known && <option value="custom">A path typed below</option>}
          </select>
        </label>
        <label className="block space-y-0.5">
          <span className={MUTED}>Or a path to a file elsewhere on this machine</span>
          <input
            className={INPUT}
            value={value}
            onChange={(event) => onChange({ ...form, [key]: event.target.value })}
          />
        </label>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {picker(draftsId, "Model for drafts", "ai_model_path")}
      {picker(speechId, "Model for speech to text", "transcription_model_path")}

      {error && (
        <p role="alert" className="text-sm text-rose-800 dark:text-rose-300">
          {error}
        </p>
      )}

      <div className="space-y-1">
        <h3 className="text-sm font-medium">Staged model files</h3>
        {models.data && <p className={MUTED}>{models.data.notice}</p>}
        {staged.length === 0 ? (
          <p className={MUTED}>
            None yet. Put a .cact file in{" "}
            <span className="font-mono">{models.data?.models_directory ?? "the models directory"}</span>, or
            import one here.
          </p>
        ) : (
          <ul aria-label="Staged model files" className="space-y-1">
            {staged.map((model: ManagedModelInfo) => (
              <li key={model.path} className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium">{model.name}</span>
                <span className={MUTED}>{megabytes(model.size_bytes)}</span>
                <span className={`${MUTED} font-mono`} title={model.sha256}>
                  {model.sha256.slice(0, 12)}…
                </span>
                {model.configured_for.length > 0 && <span className={MUTED}>in use</span>}
                <button
                  type="button"
                  disabled={busy || model.configured_for.length > 0}
                  onClick={() => void act(() => deleteAIModel(model.name))}
                  className={`${BUTTON} disabled:opacity-40`}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <label className="block space-y-0.5">
          <span className={MUTED}>Import a model file you already have (.cact)</span>
          <input type="file" accept=".cact" disabled={busy} onChange={onFile} className="block text-sm" />
        </label>
      </div>

      {status.data && (
        <div className="space-y-1">
          <h3 className="text-sm font-medium">What can run here</h3>
          <p className={MUTED}>
            {status.data.engine_available
              ? `The generation ${status.data.engine_generation} engine is staged on this machine.`
              : (status.data.engine_unavailable_reason ?? "No engine is staged.")}
          </p>
          <ul aria-label="Known models" className="space-y-0.5">
            {status.data.known_models.map((model) => (
              <li key={model.name} className="text-sm">
                <span className="font-medium">{model.name}</span>{" "}
                <span className={MUTED}>
                  {model.license}
                  {model.generation !== null && ` · needs engine ${model.generation}`}
                  {model.runnable ? " · can run here" : " · cannot run here"}
                </span>
                {!model.runnable && model.unavailable_reason && (
                  <p className={MUTED}>{model.unavailable_reason}</p>
                )}
              </li>
            ))}
          </ul>
          <p className={MUTED}>
            {status.data.offline_enforced
              ? "Downloads are blocked in this process, so no model or engine can be fetched. Staging one is always a step you take."
              : "Downloads are not blocked in this process."}
          </p>
        </div>
      )}

      {models.data && (
        <details className={MUTED}>
          <summary className="cursor-pointer">What a staged model is not</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {models.data.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
