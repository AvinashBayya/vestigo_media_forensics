import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";

import {
  errorMessage,
  getHealth,
  getLibrarySummary,
  getSearchProviders,
  getSettings,
  setDuplicateLibrary,
  startImageAnalysis,
  updateSettings,
} from "../api/client";
import {
  LIBRARY_PAGE_SIZES,
  type AnalysisOptions,
  type EditableSettings,
  type EnvironmentSettings,
  type LibraryArtifactRef,
  type LibraryPageSize,
  type AudioAnalysisOptions,
  type VideoAnalysisOptions,
} from "../api/types";
import { ErrorBanner } from "../components/Messages";
import { ErrorState, TableSkeleton } from "../components/States";
import { AUDIO_OPTION_LABELS, OPTION_LABELS, VIDEO_OPTION_LABELS } from "../components/UploadForm";
import { formatBytes, formatDateTime } from "../lib/format";
import { useSettings } from "../lib/settings";
import { useApiResource } from "../lib/useApiResource";

const CARD = "space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900";

export function SettingsPage() {
  const settingsResource = useApiResource(getSettings, "settings");
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Settings</h1>
      {settingsResource.error ? (
        <ErrorState error={settingsResource.error} onRetry={settingsResource.reload} title="Settings could not be loaded." />
      ) : !settingsResource.data ? (
        <TableSkeleton rows={3} label="Loading settings" />
      ) : (
        <>
          <DefaultsForm initial={settingsResource.data.editable} />
          <EnvironmentSection environment={settingsResource.data.environment} />
        </>
      )}
      <ToolsSection />
      <LibrarySection />
    </div>
  );
}

function DefaultsForm({ initial }: { initial: EditableSettings }) {
  const { setSettings } = useSettings();
  const [form, setForm] = useState<EditableSettings>(initial);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function change(next: EditableSettings) {
    setForm(next);
    setSaved(false);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const response = await updateSettings(form);
      setForm(response.editable);
      setSettings(response.editable);
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} aria-label="Defaults" className={CARD}>
      <h2 className="font-medium">Defaults</h2>
      <fieldset className="space-y-1">
        <legend className="mb-1 font-medium">Checks to run by default</legend>
        {(Object.keys(OPTION_LABELS) as (keyof AnalysisOptions)[]).map((key) => (
          <label key={key} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.default_analysis_options[key]}
              onChange={(event) =>
                change({ ...form, default_analysis_options: { ...form.default_analysis_options, [key]: event.target.checked } })
              }
            />
            {OPTION_LABELS[key]}
          </label>
        ))}
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Used on the upload page and by “Run analysis”. File hashes and the perceptual hash always run.
        </p>
      </fieldset>
      <fieldset className="space-y-1">
        <legend className="mb-1 font-medium">Checks to run by default on videos</legend>
        {(Object.keys(VIDEO_OPTION_LABELS) as (keyof VideoAnalysisOptions)[]).map((key) => (
          <label key={key} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.default_video_analysis_options[key]}
              onChange={(event) =>
                change({
                  ...form,
                  default_video_analysis_options: {
                    ...form.default_video_analysis_options,
                    [key]: event.target.checked,
                  },
                })
              }
            />
            {VIDEO_OPTION_LABELS[key]}
          </label>
        ))}
        <p className="text-xs text-slate-600 dark:text-slate-400">
          File hashes, media information, keyframes, and keyframe perceptual hashes always run. Keyframe OCR
          is off by default.
        </p>
      </fieldset>
      <fieldset className="space-y-1">
        <legend className="mb-1 font-medium">Checks to run by default on audio</legend>
        {(Object.keys(AUDIO_OPTION_LABELS) as (keyof AudioAnalysisOptions)[]).map((key) => (
          <label key={key} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.default_audio_analysis_options[key]}
              onChange={(event) =>
                change({
                  ...form,
                  default_audio_analysis_options: {
                    ...form.default_audio_analysis_options,
                    [key]: event.target.checked,
                  },
                })
              }
            />
            {AUDIO_OPTION_LABELS[key]}
          </label>
        ))}
        <p className="text-xs text-slate-600 dark:text-slate-400">
          File hashes and media information always run. No audio is decoded or transcribed.
        </p>
      </fieldset>
      <SearchProviderToggles form={form} onChange={change} />
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={form.auto_analyze_after_upload}
          onChange={(event) => change({ ...form, auto_analyze_after_upload: event.target.checked })}
        />
        Start the analysis automatically after each upload
      </label>
      <label className="flex items-center gap-2">
        Artifacts per Library page
        <select
          value={form.library_page_size}
          onChange={(event) => change({ ...form, library_page_size: Number(event.target.value) as LibraryPageSize })}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
        >
          {LIBRARY_PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </label>
      {error && <ErrorBanner message={error} />}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-slate-900 px-3 py-1.5 font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
        >
          Save defaults
        </button>
        {saved && (
          <span role="status" className="text-emerald-700 dark:text-emerald-400">
            Saved
          </span>
        )}
      </div>
    </form>
  );
}

/** Per-provider toggles (M5). External services are opt-in per the security policy; none is on by default. */
function SearchProviderToggles({
  form,
  onChange,
}: {
  form: EditableSettings;
  onChange: (next: EditableSettings) => void;
}) {
  const providersResource = useApiResource(getSearchProviders, "search-providers");
  const registry = providersResource.data?.providers ?? [];

  function toggle(key: string, enabled: boolean) {
    const current = new Set(form.enabled_search_providers);
    if (enabled) current.add(key);
    else current.delete(key);
    onChange({ ...form, enabled_search_providers: [...current].sort() });
  }

  return (
    <fieldset className="space-y-1">
      <legend className="mb-1 font-medium">Reverse-image search providers</legend>
      {registry.length === 0 ? (
        <p className="text-xs text-slate-600 dark:text-slate-400">Loading providers…</p>
      ) : (
        registry.map((provider) => (
          <label key={provider.key} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.enabled_search_providers.includes(provider.key)}
              onChange={(event) => toggle(provider.key, event.target.checked)}
            />
            {provider.name}
            <a
              href={provider.terms_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-slate-600 underline dark:text-slate-400"
            >
              terms
            </a>
          </label>
        ))
      )}
      <p className="text-xs text-slate-600 dark:text-slate-400">
        All providers start disabled. Enabling one only shows its link on artifact pages — media is
        shared with a provider only when you upload it there yourself, under that provider's terms.
      </p>
    </fieldset>
  );
}

function EnvironmentSection({ environment }: { environment: EnvironmentSettings }) {
  const rows: [string, string][] = [
    ["Duplicate threshold", `pHash Hamming distance ≤ ${environment.duplicate_threshold} of 64 bits`],
    ["Maximum upload size", formatBytes(environment.max_upload_bytes)],
    ["Maximum image size", `${(environment.max_image_pixels / 1_000_000).toLocaleString()} megapixels`],
    ["OCR languages", environment.ocr_languages.join(", ")],
    ["Maximum video upload size", formatBytes(environment.max_video_upload_bytes)],
    ["Maximum video duration", `${environment.max_video_duration_seconds} s`],
    [
      "Maximum video frame size",
      `${(environment.max_video_pixels / 1_000_000).toLocaleString()} megapixels`,
    ],
    ["Maximum keyframes per analysis", String(environment.max_keyframes)],
    ["Scene-change threshold", String(environment.scene_threshold)],
    ["Video tool timeout (per ffmpeg run)", `${environment.video_timeout_seconds} s`],
    ["Maximum audio upload size", formatBytes(environment.max_audio_upload_bytes)],
    ["Maximum audio duration", `${environment.max_audio_duration_seconds} s`],
    ["Tool timeout", `${environment.tool_timeout_seconds} s`],
    ["OCR timeout (per pass)", `${environment.ocr_timeout_seconds} s`],
    ["Analysis workers", `${environment.job_workers} (${environment.job_mode})`],
    ["Log level", environment.log_level],
    ["Data folder", environment.data_dir],
    ["Vestigo version", environment.app_version],
    ["Database schema", environment.schema_revision ?? "unknown"],
  ];
  return (
    <section aria-label="Environment" className={CARD}>
      <h2 className="font-medium">Environment (read-only)</h2>
      <p className="text-xs text-slate-600 dark:text-slate-400">
        Set with VESTIGO_* environment variables or the .env file. Restart the backend after changing them.
      </p>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="font-medium">{label}</dt>
            <dd className="break-all">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function ToolsSection() {
  const { data, error, reload } = useApiResource(getHealth, "health");
  return (
    <section aria-label="Tools" className={CARD}>
      <h2 className="font-medium">Tools</h2>
      {error && <ErrorState error={error} onRetry={reload} title="Tool status could not be loaded." />}
      {data && (
        <table className="w-full text-left">
          <thead className="text-xs text-slate-600 dark:text-slate-400">
            <tr>
              <th className="py-1 pr-3 font-medium">Tool</th>
              <th className="py-1 pr-3 font-medium">Status</th>
              <th className="py-1 pr-3 font-medium">Version</th>
              <th className="py-1 font-medium">Used for</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.tools).map(([name, tool]) => (
              <tr key={name} className="border-t border-slate-200 dark:border-slate-800">
                <td className="py-1 pr-3 font-mono">{name}</td>
                <td className="py-1 pr-3">{tool.status === "ok" ? "Available" : tool.status === "missing" ? "Not installed" : "Not working"}</td>
                <td className="py-1 pr-3">{tool.version ?? "—"}</td>
                <td className="py-1">{tool.used_in}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function LibrarySection() {
  const [version, setVersion] = useState(0);
  const { data, error, reload } = useApiResource(getLibrarySummary, `summary:${version}`);
  const [started, setStarted] = useState<ReadonlySet<string>>(new Set());
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => setActionError(null), [version]);

  async function analyse(artifactId: string) {
    setActionError(null);
    try {
      await startImageAnalysis(artifactId);
      setStarted((current) => new Set(current).add(artifactId));
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  async function include(artifactId: string) {
    setActionError(null);
    try {
      await setDuplicateLibrary(artifactId, true);
      setVersion((n) => n + 1);
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  return (
    <section aria-label="Duplicate library and storage" className={CARD}>
      <h2 className="font-medium">Duplicate library and storage</h2>
      {error && <ErrorState error={error} onRetry={reload} title="The library summary could not be loaded." />}
      {actionError && <ErrorBanner message={actionError} />}
      {data && (
        <>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
            <dt className="font-medium">Artifacts</dt>
            <dd>{data.artifact_count}</dd>
            <dt className="font-medium">Searchable for duplicates</dt>
            <dd>{data.indexed_count}</dd>
            <dt className="font-medium">Not analysed yet</dt>
            <dd>{data.not_indexed_count} (found by duplicate search only if byte-identical)</dd>
            <dt className="font-medium">Excluded from duplicate search</dt>
            <dd>{data.excluded_count}</dd>
            <dt className="font-medium">Storage: originals</dt>
            <dd>{formatBytes(data.storage.original_bytes)}</dd>
            <dt className="font-medium">Storage: derived files</dt>
            <dd>{formatBytes(data.storage.derived_bytes)}</dd>
          </dl>
          <ArtifactRefs
            title="Not analysed yet"
            refs={data.not_indexed}
            total={data.not_indexed_count}
            action={(id) =>
              started.has(id) ? (
                <span className="text-xs">Analysis started</span>
              ) : (
                <button type="button" onClick={() => void analyse(id)} className="text-sky-700 underline dark:text-sky-400">
                  Run analysis
                </button>
              )
            }
          />
          <ArtifactRefs
            title="Excluded from duplicate search"
            refs={data.excluded}
            total={data.excluded_count}
            action={(id) => (
              <button type="button" onClick={() => void include(id)} className="text-sky-700 underline dark:text-sky-400">
                Include again
              </button>
            )}
          />
        </>
      )}
    </section>
  );
}

function ArtifactRefs({
  title,
  refs,
  total,
  action,
}: {
  title: string;
  refs: LibraryArtifactRef[];
  total: number;
  action: (artifactId: string) => ReactNode;
}) {
  if (total === 0) return null;
  return (
    <div className="space-y-1" role="group" aria-label={title}>
      <h3 className="font-medium">{title}</h3>
      <ul className="space-y-1">
        {refs.map((ref) => (
          <li key={ref.artifact_id} className="flex flex-wrap items-center gap-3">
            <Link to={`/artifacts/${ref.artifact_id}`} className="text-sky-700 underline dark:text-sky-400">
              {ref.filename}
            </Link>
            <span className="text-xs text-slate-600 dark:text-slate-400">{formatDateTime(ref.created_at)}</span>
            {action(ref.artifact_id)}
          </li>
        ))}
      </ul>
      {total > refs.length && (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Showing the newest {refs.length} of {total}.
        </p>
      )}
    </div>
  );
}
