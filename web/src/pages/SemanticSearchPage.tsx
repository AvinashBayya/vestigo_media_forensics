import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { askQuestion, errorMessage, semanticSearch } from "../api/client";
import type { AnswerResponse, SearchHit, SemanticSearchResponse } from "../api/types";
import { ErrorBanner } from "../components/Messages";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";
const CARD =
  "space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900";
const BUTTON =
  "rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900";

const SOURCE_LABELS: Record<string, string> = {
  analyst_notes: "my notes",
  record_notes: "my notes on a record",
  ocr_text: "text found by OCR",
  metadata: "embedded metadata",
  transcript: "a transcript",
  location_candidate: "a location candidate",
  external_lead: "an external lead",
};

function Hits({ hits, label }: { hits: SearchHit[]; label: string }) {
  if (hits.length === 0) return null;
  return (
    <ul aria-label={label} className="space-y-2">
      {hits.map((hit, index) => (
        <li key={`${hit.artifact_id}-${hit.source_kind}-${index}`} className="space-y-0.5">
          <p className="flex flex-wrap items-baseline gap-2">
            <Link to={`/artifacts/${hit.artifact_id}`} className="font-medium underline">
              {hit.filename ?? hit.artifact_id}
            </Link>
            <span className={MUTED}>
              {SOURCE_LABELS[hit.source_kind] ?? hit.source_kind} · match {hit.score.toFixed(2)}
            </span>
          </p>
          <p className="rounded-md bg-slate-50 px-2 py-1 dark:bg-slate-800">{hit.text}</p>
        </li>
      ))}
    </ul>
  );
}

/** Local search and question answering over the analyst's own material (Pass 1). */
export function SemanticSearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SemanticSearchResponse | null>(null);
  const [answer, setAnswer] = useState<AnswerResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(event: FormEvent, mode: "search" | "ask") {
    event.preventDefault();
    setError(null);
    setBusy(true);
    setAnswer(null);
    setResults(null);
    try {
      if (mode === "search") setResults(await semanticSearch(query));
      else setAnswer(await askQuestion(query));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Search my material</h1>
      <form onSubmit={(event) => void run(event, "search")} aria-label="Semantic search" className={CARD}>
        <p className={MUTED}>
          Searches only what you hold on this machine — your notes, OCR text, transcripts, selected
          metadata, your leads and location candidates. Nothing is sent anywhere, and results are
          your own records, not findings.
        </p>
        <label className="block space-y-0.5">
          <span className={MUTED}>Words to look for, or a question to ask</span>
          <input
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
          />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" disabled={busy || !query.trim()} className={BUTTON}>
            Search
          </button>
          <button
            type="button"
            disabled={busy || !query.trim()}
            onClick={(event) => void run(event as unknown as FormEvent, "ask")}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-40 dark:border-slate-600"
          >
            Ask a question
          </button>
        </div>
        {error && <ErrorBanner message={error} />}
      </form>

      {results && (
        <section aria-labelledby="results-heading" className={CARD}>
          <h2 id="results-heading" className="font-medium">
            Matches in my material
          </h2>
          {results.model && <p className={MUTED}>Indexed with {results.model}.</p>}
          {results.hits.length === 0 ? (
            <p>
              Nothing matched. Artifacts are searchable once you index them from the AI assistant
              panel on the artifact page.
            </p>
          ) : (
            <Hits hits={results.hits} label="Search results" />
          )}
        </section>
      )}

      {answer && (
        <section aria-labelledby="answer-heading" className={CARD}>
          <h2 id="answer-heading" className="font-medium">
            Answer
          </h2>
          <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
            {answer.notice}
          </p>
          {answer.answer ? (
            <p className="whitespace-pre-wrap">{answer.answer}</p>
          ) : (
            <p className={MUTED}>
              No answer was drafted, so the matching material is below exactly as you recorded it.
            </p>
          )}
          <h3 className="font-medium">Sources — read these</h3>
          {answer.sources.length === 0 ? (
            <p>Nothing in your indexed material matched this question.</p>
          ) : (
            <Hits hits={answer.sources} label="Answer sources" />
          )}
        </section>
      )}
    </div>
  );
}
