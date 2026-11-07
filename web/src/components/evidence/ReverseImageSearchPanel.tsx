import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import {
  createExternalLead,
  deleteExternalLead,
  derivedContentUrl,
  downloadUrl,
  errorMessage,
  getSearchProviders,
  listExternalLeads,
  updateExternalLead,
} from "../../api/client";
import type {
  ExternalLead,
  ExternalLeadsResponse,
  KeyframesSection,
  MediaType,
  ReviewState,
  SearchProvidersResponse,
} from "../../api/types";
import { REVIEW_STATES } from "../../api/types";
import { REVIEW_LABELS, formatDateTime, formatSeconds } from "../../lib/format";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";
const INPUT =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900";
const BUTTON = "rounded-md border border-slate-300 px-2 py-1 text-sm font-medium dark:border-slate-600";

interface ReverseImageSearchPanelProps {
  artifactId: string;
  mediaType: MediaType;
  /** The viewed analysis's keyframes: the only video search subjects. Previews are never offered. */
  keyframes: KeyframesSection | null;
  /** Called after a lead is recorded, edited, or deleted, so siblings (custody) can refresh. */
  onLeadsChanged?: () => void;
}

export function ReverseImageSearchPanel({
  artifactId,
  mediaType,
  keyframes,
  onLeadsChanged,
}: ReverseImageSearchPanelProps) {
  const headingId = useId();
  const [providers, setProviders] = useState<SearchProvidersResponse | null>(null);
  const [leads, setLeads] = useState<ExternalLeadsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The selected keyframe's derived_file_id; null means the original image (image artifacts only).
  const [subject, setSubject] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [providerList, leadList] = await Promise.all([getSearchProviders(), listExternalLeads(artifactId)]);
      setProviders(providerList);
      setLeads(leadList);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [artifactId]);

  useEffect(() => {
    void load();
  }, [load]);

  const frames = keyframes?.frames.filter((frame) => frame.derived_file_id) ?? [];
  // Only a keyframe of THIS artifact's viewed analysis counts: a selection left over from another
  // artifact or an earlier analysis self-heals to "nothing selected" instead of leaking.
  const validSubject =
    mediaType === "video" && frames.some((frame) => frame.derived_file_id === subject) ? subject : null;
  const subjectReady = mediaType === "image" || validSubject !== null;

  function changed() {
    void load();
    onLeadsChanged?.();
  }

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-lg border border-slate-200 bg-white shadow-xs dark:border-slate-800 dark:bg-slate-900"
    >
      <header className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 id={headingId} className="font-medium">
          Reverse-image search (external)
        </h2>
      </header>
      <div className="space-y-4 px-4 py-3 text-sm">
        {error ? (
          <div role="alert" className="space-y-2">
            <p className="text-rose-800 dark:text-rose-300">Could not load the search tools: {error}</p>
            <button type="button" onClick={() => void load()} className={BUTTON}>
              Retry
            </button>
          </div>
        ) : providers === null || leads === null ? (
          <p className={MUTED}>Loading…</p>
        ) : (
          <>
            <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
              {providers.notice}
            </p>

            {mediaType === "video" && (
              <fieldset>
                <legend className="mb-1 font-medium">Search subject (a keyframe of this analysis)</legend>
                {frames.length === 0 ? (
                  <p className={MUTED}>
                    No keyframes are available. Run an analysis to extract keyframes; the search subject
                    is always a keyframe extracted from the original video — never the re-encoded
                    playable preview.
                  </p>
                ) : (
                  <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                    {frames.map((frame) => (
                      <li key={frame.seq}>
                        <label className="block cursor-pointer space-y-1">
                          <input
                            type="radio"
                            name="search-subject"
                            className="sr-only"
                            checked={validSubject === frame.derived_file_id}
                            onChange={() => setSubject(frame.derived_file_id)}
                          />
                          <img
                            src={derivedContentUrl(artifactId, frame.derived_file_id!)}
                            alt={`Keyframe ${frame.seq} at ${formatSeconds(frame.timestamp)}`}
                            loading="lazy"
                            className={`aspect-video w-full rounded object-contain ring-2 ${
                              validSubject === frame.derived_file_id
                                ? "bg-sky-100 ring-sky-600 dark:bg-sky-950"
                                : "bg-slate-100 ring-transparent dark:bg-slate-800"
                            }`}
                          />
                          <span className={`block text-center ${MUTED}`}>
                            #{frame.seq} · {formatSeconds(frame.timestamp)}
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                )}
              </fieldset>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <a
                href={
                  subjectReady
                    ? downloadUrl(artifactId, mediaType === "video" ? validSubject : null)
                    : undefined
                }
                aria-disabled={!subjectReady}
                className={`${BUTTON} ${subjectReady ? "" : "pointer-events-none opacity-40"}`}
                download
              >
                {mediaType === "video" ? "Download selected keyframe" : "Download original image"}
              </a>
              <span className={MUTED}>
                Save the exact subject file, then upload it manually on the provider's page.
              </span>
            </div>

            <div>
              <h3 className="mb-1 font-medium">Providers</h3>
              <ul className="space-y-2">
                {providers.providers.map((provider) => (
                  <li key={provider.key} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    {provider.enabled ? (
                      <a
                        href={provider.landing_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-medium underline"
                      >
                        Open {provider.name}
                      </a>
                    ) : (
                      <span className="text-slate-500">{provider.name} — enable in Settings</span>
                    )}
                    {provider.enabled && (
                      <>
                        <span className={MUTED}>{provider.instructions}</span>
                        <a href={provider.terms_url} target="_blank" rel="noopener noreferrer" className={MUTED}>
                          (terms)
                        </a>
                      </>
                    )}
                  </li>
                ))}
              </ul>
              <p className={`mt-1 ${MUTED}`}>
                Vestigo cannot observe or record what happens after a provider page opens — whether a
                search ran, or what it returned. Record what you find below.
              </p>
            </div>

            <LeadForm
              artifactId={artifactId}
              subject={mediaType === "video" ? validSubject : null}
              subjectReady={subjectReady}
              onRecorded={changed}
            />

            <LeadsList artifactId={artifactId} response={leads} keyframes={keyframes} onChanged={changed} />
          </>
        )}
      </div>
    </section>
  );
}

function LeadForm({
  artifactId,
  subject,
  subjectReady,
  onRecorded,
}: {
  artifactId: string;
  subject: string | null;
  subjectReady: boolean;
  onRecorded: () => void;
}) {
  const [provider, setProvider] = useState("");
  const [resultUrl, setResultUrl] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [claimed, setClaimed] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await createExternalLead(artifactId, {
        provider,
        result_url: resultUrl,
        ...(imageUrl && { image_url: imageUrl }),
        ...(claimed && { claimed_published_at: claimed }),
        ...(notes && { notes }),
        ...(subject && { derived_file_id: subject }),
      });
      setProvider("");
      setResultUrl("");
      setImageUrl("");
      setClaimed("");
      setNotes("");
      onRecorded();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-2" aria-label="Record an external lead">
      <h3 className="font-medium">Record an external lead</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-0.5">
          <span className={MUTED}>Provider</span>
          <input className={INPUT} value={provider} onChange={(e) => setProvider(e.target.value)} required />
        </label>
        <label className="space-y-0.5">
          <span className={MUTED}>Result page URL</span>
          <input
            className={INPUT}
            type="url"
            value={resultUrl}
            onChange={(e) => setResultUrl(e.target.value)}
            required
          />
        </label>
        <label className="space-y-0.5">
          <span className={MUTED}>Image URL (optional)</span>
          <input className={INPUT} type="url" value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} />
        </label>
        <label className="space-y-0.5">
          <span className={MUTED}>Publication date as shown on the page (optional, unverified)</span>
          <input className={INPUT} value={claimed} onChange={(e) => setClaimed(e.target.value)} />
        </label>
      </div>
      <label className="block space-y-0.5">
        <span className={MUTED}>Notes</span>
        <textarea className={INPUT} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {error && (
        <p role="alert" className="text-rose-800 dark:text-rose-300">
          {error}
        </p>
      )}
      <button type="submit" disabled={saving || !subjectReady} className={`${BUTTON} disabled:opacity-40`}>
        Record lead
      </button>
      {!subjectReady && <span className={`ml-2 ${MUTED}`}>Select the searched keyframe first.</span>}
    </form>
  );
}

function LeadsList({
  artifactId,
  response,
  keyframes,
  onChanged,
}: {
  artifactId: string;
  response: ExternalLeadsResponse;
  keyframes: KeyframesSection | null;
  onChanged: () => void;
}) {
  return (
    <div>
      <h3 className="mb-1 font-medium">Recorded leads</h3>
      <p className={MUTED}>{response.notice}</p>
      {response.leads.length === 0 ? (
        <p className={`mt-1 ${MUTED}`}>No leads recorded yet.</p>
      ) : (
        <ul aria-label="External leads" className="mt-2 space-y-3">
          {response.leads.map((lead) => (
            <LeadRow
              key={lead.lead_id}
              artifactId={artifactId}
              lead={lead}
              keyframes={keyframes}
              onChanged={onChanged}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function LeadRow({
  artifactId,
  lead,
  keyframes,
  onChanged,
}: {
  artifactId: string;
  lead: ExternalLead;
  keyframes: KeyframesSection | null;
  onChanged: () => void;
}) {
  const [notes, setNotes] = useState(lead.notes);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const frame = keyframes?.frames.find((f) => f.derived_file_id === lead.derived_file_id);

  async function patch(update: Parameters<typeof updateExternalLead>[2]) {
    setError(null);
    try {
      await updateExternalLead(artifactId, lead.lead_id, update);
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function remove() {
    setError(null);
    try {
      await deleteExternalLead(artifactId, lead.lead_id);
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <li className="space-y-1 rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <p className="flex flex-wrap items-baseline gap-2">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold dark:bg-slate-800">
          EXTERNAL
        </span>
        <span className="font-medium">{lead.provider}</span>
        <a href={lead.result_url} target="_blank" rel="noopener noreferrer" className="break-all underline">
          {lead.result_url}
        </a>
      </p>
      <p className={MUTED}>
        Recorded {formatDateTime(lead.recorded_at)}
        {lead.updated_at && ` · edited ${formatDateTime(lead.updated_at)}`}
        {lead.derived_file_id &&
          ` · from keyframe ${frame ? `#${frame.seq} (${formatSeconds(frame.timestamp)})` : lead.derived_file_id}`}
      </p>
      {lead.claimed_published_at && (
        <p className={MUTED}>
          Publication date (analyst-reported, unverified): {lead.claimed_published_at}
        </p>
      )}
      {lead.image_url && (
        <p className={MUTED}>
          Image URL:{" "}
          <a href={lead.image_url} target="_blank" rel="noopener noreferrer" className="break-all underline">
            {lead.image_url}
          </a>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-xs">
          Review:
          <select
            className="rounded-md border border-slate-300 bg-white px-1 py-0.5 dark:border-slate-700 dark:bg-slate-900"
            value={lead.review_state}
            onChange={(event) => void patch({ review_state: event.target.value as ReviewState })}
          >
            {REVIEW_STATES.map((state) => (
              <option key={state} value={state}>
                {REVIEW_LABELS[state]}
              </option>
            ))}
          </select>
        </label>
        {confirming ? (
          <>
            <button type="button" onClick={() => void remove()} className={`${BUTTON} text-rose-800 dark:text-rose-300`}>
              Confirm delete
            </button>
            <button type="button" onClick={() => setConfirming(false)} className={BUTTON}>
              Keep
            </button>
          </>
        ) : (
          <button type="button" onClick={() => setConfirming(true)} className={BUTTON}>
            Delete lead
          </button>
        )}
      </div>
      <label className="block space-y-0.5">
        <span className={MUTED}>Notes</span>
        <textarea className={INPUT} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {notes !== lead.notes && (
        <button type="button" onClick={() => void patch({ notes })} className={BUTTON}>
          Save notes
        </button>
      )}
      {error && (
        <p role="alert" className="text-rose-800 dark:text-rose-300">
          {error}
        </p>
      )}
    </li>
  );
}
