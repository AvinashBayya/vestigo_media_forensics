import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import {
  createAIDraft,
  createTranscript,
  deleteAIDraft,
  deleteTranscript,
  errorMessage,
  getAIStatus,
  listAIDrafts,
  listTranscripts,
  updateTranscript,
  decideDraftField,
} from "../../api/client";
import type {
  AIDraft,
  AIDraftsResponse,
  AIStatus,
  DraftField,
  DraftSource,
  MediaType,
  ReviewState,
  Transcript,
  TranscriptsResponse,
} from "../../api/types";
import { REVIEW_STATES } from "../../api/types";
import { REVIEW_LABELS, formatDateTime, formatSeconds } from "../../lib/format";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";
const INPUT =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900";
const BUTTON = "rounded-md border border-slate-300 px-2 py-1 text-sm font-medium dark:border-slate-600";
const WARN =
  "rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100";

const SOURCE_LABELS: Record<DraftSource, string> = {
  metadata: "Embedded metadata",
  ocr_text: "Text found by OCR",
  analyst_notes: "My own notes",
  transcript: "A transcript",
};

function modelLine(model: Record<string, unknown>): string {
  const parts = [model.name, model.version && `v${model.version}`, model.quantization, model.license]
    .filter(Boolean)
    .map(String);
  return parts.join(" · ");
}

interface AIAssistantPanelProps {
  artifactId: string;
  mediaType: MediaType;
  onChanged?: () => void;
}

/** AI drafts and machine transcripts: labelled, reviewable, and never evidence (Pass 1). */
export function AIAssistantPanel({ artifactId, mediaType, onChanged }: AIAssistantPanelProps) {
  const headingId = useId();
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [drafts, setDrafts] = useState<AIDraftsResponse | null>(null);
  const [transcripts, setTranscripts] = useState<TranscriptsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [statusResult, draftResult, transcriptResult] = await Promise.all([
        getAIStatus(),
        listAIDrafts(artifactId),
        listTranscripts(artifactId),
      ]);
      setStatus(statusResult);
      setDrafts(draftResult);
      setTranscripts(transcriptResult);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [artifactId]);

  useEffect(() => {
    void load();
  }, [load]);

  function changed() {
    void load();
    onChanged?.();
  }

  const hasAudio = mediaType === "audio" || mediaType === "video";

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-lg border border-slate-200 bg-white shadow-xs dark:border-slate-800 dark:bg-slate-900"
    >
      <header className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <h2 id={headingId} className="font-medium">
          AI assistant (drafts, not evidence)
        </h2>
      </header>
      <div className="space-y-4 px-4 py-3 text-sm">
        {error ? (
          <div role="alert" className="space-y-2">
            <p className="text-rose-800 dark:text-rose-300">The AI assistant could not load: {error}</p>
            <button type="button" onClick={() => void load()} className={BUTTON}>
              Retry
            </button>
          </div>
        ) : status === null || drafts === null || transcripts === null ? (
          <p className={MUTED}>Loading…</p>
        ) : (
          <>
            <p className={WARN}>{status.label}</p>
            <p className={MUTED}>
              Everything here is produced on this machine by a local model and is kept apart from the
              evidence: it is never a finding, and nothing is written back onto metadata or evidence.
              {status.telemetry_disabled && " Vendor telemetry is disabled."}
              {status.offline_enforced && " Downloads are blocked, so no model can be fetched."}
            </p>

            <DraftsSection
              artifactId={artifactId}
              status={status}
              response={drafts}
              onChanged={changed}
            />

            {hasAudio && (
              <TranscriptsSection
                artifactId={artifactId}
                status={status}
                response={transcripts}
                onChanged={changed}
              />
            )}
          </>
        )}
      </div>
    </section>
  );
}

function DraftsSection({
  artifactId,
  status,
  response,
  onChanged,
}: {
  artifactId: string;
  status: AIStatus;
  response: AIDraftsResponse;
  onChanged: () => void;
}) {
  const [source, setSource] = useState<DraftSource>("metadata");
  const [fieldNames, setFieldNames] = useState("city, date, device");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const fields = fieldNames
        .split(",")
        .map((name) => name.trim())
        .filter(Boolean);
      await createAIDraft(artifactId, { source_kind: source, fields });
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <h3 className="font-medium">Proposed fields</h3>
      <p className={MUTED}>{response.notice}</p>
      {!status.drafts_available && (
        <p className={MUTED}>{status.drafts_unavailable_reason}</p>
      )}
      <form onSubmit={(event) => void submit(event)} className="space-y-2" aria-label="Ask for a draft">
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="space-y-0.5">
            <span className={MUTED}>Read from</span>
            <select
              className={INPUT}
              value={source}
              onChange={(event) => setSource(event.target.value as DraftSource)}
            >
              {(Object.keys(SOURCE_LABELS) as DraftSource[]).map((key) => (
                <option key={key} value={key}>
                  {SOURCE_LABELS[key]}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-0.5">
            <span className={MUTED}>Fields to look for (comma separated)</span>
            <input className={INPUT} value={fieldNames} onChange={(e) => setFieldNames(e.target.value)} />
          </label>
        </div>
        {error && (
          <p role="alert" className="text-rose-800 dark:text-rose-300">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || !status.drafts_available} className={`${BUTTON} disabled:opacity-40`}>
          Ask the local model
        </button>
      </form>

      {response.drafts.length === 0 ? (
        <p className={MUTED}>No drafts yet.</p>
      ) : (
        <ul aria-label="AI drafts" className="space-y-3">
          {response.drafts.map((draft) => (
            <DraftRow key={draft.draft_id} artifactId={artifactId} draft={draft} onChanged={onChanged} />
          ))}
        </ul>
      )}
    </div>
  );
}

function DraftRow({
  artifactId,
  draft,
  onChanged,
}: {
  artifactId: string;
  draft: AIDraft;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);

  async function decide(field: DraftField, action: "accepted" | "rejected" | "edited", value?: string) {
    setError(null);
    try {
      await decideDraftField(artifactId, draft.draft_id, { field: field.name, action, ...(value ? { value } : {}) });
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <li className="space-y-2 rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <p className={MUTED}>
        From {SOURCE_LABELS[draft.source_kind as DraftSource] ?? draft.source_kind} ·{" "}
        {modelLine(draft.model)} · {formatDateTime(draft.created_at)} · {draft.status}
      </p>
      <ul aria-label={`Fields proposed in ${draft.draft_id}`} className="space-y-2">
        {draft.fields.map((field) => (
          <FieldRow key={field.name} field={field} onDecide={decide} />
        ))}
      </ul>
      {draft.fields.length === 0 && (
        <p className={MUTED}>The model returned no values for the requested fields.</p>
      )}
      {draft.reasoning && (
        <details className={MUTED}>
          <summary className="cursor-pointer">The model's stated reasoning (not a finding)</summary>
          <p className="mt-1">{draft.reasoning}</p>
        </details>
      )}
      {draft.warnings.map((warning) => (
        <p key={warning} className="text-amber-900 dark:text-amber-200">
          {warning}
        </p>
      ))}
      <button
        type="button"
        onClick={() => {
          void deleteAIDraft(artifactId, draft.draft_id).then(onChanged, (err) => setError(errorMessage(err)));
        }}
        className={BUTTON}
      >
        Delete draft
      </button>
      {error && (
        <p role="alert" className="text-rose-800 dark:text-rose-300">
          {error}
        </p>
      )}
    </li>
  );
}

function FieldRow({
  field,
  onDecide,
}: {
  field: DraftField;
  onDecide: (field: DraftField, action: "accepted" | "rejected" | "edited", value?: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(field.edited_value ?? field.value);

  return (
    <li className="space-y-1">
      <p className="flex flex-wrap items-baseline gap-2">
        <span className="font-medium">{field.name}</span>
        <span>{field.value}</span>
        <span className={MUTED}>
          {field.confidence != null
            ? `model's own confidence ${Math.round(field.confidence * 100)}%`
            : "no confidence given by the model"}
        </span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs dark:bg-slate-800">{field.status}</span>
      </p>
      {field.edited_value && (
        <p className={MUTED}>
          Your version: <span className="text-slate-900 dark:text-slate-100">{field.edited_value}</span>
        </p>
      )}
      {editing ? (
        <div className="flex flex-wrap items-center gap-2">
          <input className={`${INPUT} max-w-sm`} value={value} onChange={(e) => setValue(e.target.value)} />
          <button
            type="button"
            onClick={() => {
              onDecide(field, "edited", value);
              setEditing(false);
            }}
            className={BUTTON}
          >
            Save my version
          </button>
          <button type="button" onClick={() => setEditing(false)} className={BUTTON}>
            Cancel
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => onDecide(field, "accepted")} className={BUTTON}>
            Accept
          </button>
          <button type="button" onClick={() => setEditing(true)} className={BUTTON}>
            Edit
          </button>
          <button type="button" onClick={() => onDecide(field, "rejected")} className={BUTTON}>
            Reject
          </button>
        </div>
      )}
    </li>
  );
}

function TranscriptsSection({
  artifactId,
  status,
  response,
  onChanged,
}: {
  artifactId: string;
  status: AIStatus;
  response: TranscriptsResponse;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function transcribe() {
    setError(null);
    setBusy(true);
    try {
      await createTranscript(artifactId);
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-800">
      <h3 className="font-medium">Transcripts</h3>
      <p className={MUTED}>{response.notice}</p>
      {!status.transcription_available && (
        <p className={MUTED}>{status.transcription_unavailable_reason}</p>
      )}
      <button
        type="button"
        onClick={() => void transcribe()}
        disabled={busy || !status.transcription_available}
        className={`${BUTTON} disabled:opacity-40`}
      >
        Transcribe audio locally
      </button>
      {error && (
        <p role="alert" className="text-rose-800 dark:text-rose-300">
          {error}
        </p>
      )}
      {response.transcripts.length === 0 ? (
        <p className={MUTED}>No transcripts yet.</p>
      ) : (
        <ul aria-label="Transcripts" className="space-y-3">
          {response.transcripts.map((transcript) => (
            <TranscriptRow
              key={transcript.transcript_id}
              artifactId={artifactId}
              transcript={transcript}
              onChanged={onChanged}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function TranscriptRow({
  artifactId,
  transcript,
  onChanged,
}: {
  artifactId: string;
  transcript: Transcript;
  onChanged: () => void;
}) {
  const [edited, setEdited] = useState(transcript.edited_text ?? "");
  const [error, setError] = useState<string | null>(null);

  async function patch(update: { edited_text?: string; review_state?: ReviewState }) {
    setError(null);
    try {
      await updateTranscript(artifactId, transcript.transcript_id, update);
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <li className="space-y-2 rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <p className={MUTED}>
        {modelLine(transcript.model)}
        {transcript.language && ` · ${transcript.language}`}
        {transcript.duration_seconds != null && ` · ${formatSeconds(transcript.duration_seconds)}`} ·
        Recorded {formatDateTime(transcript.created_at)}
        {transcript.derived_file_id && " · from the extracted audio track"}
      </p>
      <ol aria-label="Transcript segments" className="space-y-1">
        {transcript.segments.map((segment, index) => (
          <li key={`${segment.start}-${index}`} className="flex gap-2">
            <span className={`shrink-0 font-mono ${MUTED}`}>{formatSeconds(segment.start)}</span>
            <span>{segment.text}</span>
          </li>
        ))}
      </ol>
      {transcript.warnings.map((warning) => (
        <p key={warning} className="text-amber-900 dark:text-amber-200">
          {warning}
        </p>
      ))}
      <label className="block space-y-0.5">
        <span className={MUTED}>My corrected text (the model's text above is always kept)</span>
        <textarea className={INPUT} rows={2} value={edited} onChange={(e) => setEdited(e.target.value)} />
      </label>
      <div className="flex flex-wrap items-center gap-2">
        {edited !== (transcript.edited_text ?? "") && (
          <button type="button" onClick={() => void patch({ edited_text: edited })} className={BUTTON}>
            Save my version
          </button>
        )}
        <label className="flex items-center gap-1 text-xs">
          Review:
          <select
            className="rounded-md border border-slate-300 bg-white px-1 py-0.5 dark:border-slate-700 dark:bg-slate-900"
            value={transcript.review_state}
            onChange={(event) => void patch({ review_state: event.target.value as ReviewState })}
          >
            {REVIEW_STATES.map((state) => (
              <option key={state} value={state}>
                {REVIEW_LABELS[state]}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => {
            void deleteTranscript(artifactId, transcript.transcript_id).then(onChanged, (err) =>
              setError(errorMessage(err)),
            );
          }}
          className={BUTTON}
        >
          Delete transcript
        </button>
      </div>
      {error && (
        <p role="alert" className="text-rose-800 dark:text-rose-300">
          {error}
        </p>
      )}
    </li>
  );
}
