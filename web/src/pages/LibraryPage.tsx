import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import { listArtifacts, toSearchParams } from "../api/client";
import type { ArtifactSort } from "../api/types";
import { ArtifactTable } from "../components/library/ArtifactTable";
import { BulkReviewBar, describeBulkResult, type BulkOutcome } from "../components/library/BulkReviewBar";
import { FilterBar } from "../components/library/FilterBar";
import { ErrorBanner, EvidenceNotice, InfoBanner } from "../components/Messages";
import { EmptyState, ErrorState, TableSkeleton } from "../components/States";
import {
  clearFilters,
  isFiltered,
  parseLibraryState,
  toArtifactQuery,
  toUrlParams,
  type LibraryState,
} from "../lib/libraryState";
import { useApiResource } from "../lib/useApiResource";

export const DEFAULT_PAGE_SIZE = 25;

export const UPLOAD_BUTTON =
  "inline-flex items-center rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";

export function LibraryPage({ pageSize = DEFAULT_PAGE_SIZE }: { pageSize?: number }) {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const notice = (location.state as { notice?: string } | null)?.notice;
  const state = parseLibraryState(params);
  const query = toArtifactQuery(state, pageSize);
  const key = toSearchParams(query).toString();
  const { data, error, loading, reload } = useApiResource(() => listArtifacts(query), key);
  const filtered = isFiltered(state);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [bulkOutcome, setBulkOutcome] = useState<BulkOutcome | null>(null);

  // Selection belongs to the rows on screen: a new search, filter, sort, or page clears it.
  useEffect(() => setSelected(new Set()), [key]);

  function select(artifactIds: string[], isSelected: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      for (const id of artifactIds) {
        if (isSelected) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  function onBulkDone(outcome: BulkOutcome) {
    setBulkOutcome(outcome);
    if (outcome.kind === "success") setSelected(new Set());
    reload();
  }

  const update = useCallback(
    (changes: Partial<LibraryState>, options: { replace?: boolean; keepPage?: boolean } = {}) => {
      setParams(
        (current) => {
          const next = { ...parseLibraryState(current), ...changes };
          if (!options.keepPage && !("page" in changes)) next.page = 1;
          return toUrlParams(next);
        },
        { replace: options.replace },
      );
    },
    [setParams],
  );

  function onSort(sort: ArtifactSort) {
    if (sort === state.sort) update({ order: state.order === "asc" ? "desc" : "asc" });
    else update({ sort, order: sort === "created_at" || sort === "size_bytes" ? "desc" : "asc" });
  }

  const total = data?.total ?? 0;
  const first = total === 0 ? 0 : (state.page - 1) * pageSize + 1;
  const last = Math.min(state.page * pageSize, total);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Library</h1>
        <Link to="/upload" className={UPLOAD_BUTTON}>
          Upload an image
        </Link>
      </div>
      {notice && <InfoBanner>{notice}</InfoBanner>}
      {bulkOutcome?.kind === "success" && <InfoBanner>{describeBulkResult(bulkOutcome.result)}</InfoBanner>}
      {bulkOutcome?.kind === "error" && <ErrorBanner message={`Bulk review failed. ${bulkOutcome.message}`} />}
      <EvidenceNotice />
      <FilterBar
        state={state}
        counts={data?.counts_by_review_state ?? null}
        onChange={update}
        onClear={() => setParams(toUrlParams(clearFilters(state)))}
        filtered={filtered}
      />

      <section aria-label="Artifacts" aria-busy={loading} className="space-y-3">
        {error ? (
          <ErrorState error={error} onRetry={reload} title="The Library could not be loaded." />
        ) : data === null ? (
          <TableSkeleton label="Loading the Library" />
        ) : data.items.length === 0 ? (
          filtered ? (
            <EmptyState
              title="No artifacts match"
              action={
                <button type="button" onClick={() => setParams(toUrlParams(clearFilters(state)))} className="text-sm text-sky-700 underline dark:text-sky-400">
                  Clear filters
                </button>
              }
            >
              Try a different search or fewer filters.
            </EmptyState>
          ) : state.page > 1 ? (
            <EmptyState
              title="This page is empty"
              action={
                <button type="button" onClick={() => update({ page: 1 })} className="text-sm text-sky-700 underline dark:text-sky-400">
                  Go to the first page
                </button>
              }
            />
          ) : (
            <EmptyState
              title="No artifacts yet"
              action={
                <Link to="/upload" className={UPLOAD_BUTTON}>
                  Upload an image
                </Link>
              }
            >
              Uploaded images and their evidence will be listed here.
            </EmptyState>
          )
        ) : (
          <>
            <p role="status" className="text-sm text-slate-600 dark:text-slate-400">
              Showing {first}–{last} of {total} {total === 1 ? "artifact" : "artifacts"}
              {loading && " · Updating…"}
            </p>
            {selected.size > 0 && (
              <BulkReviewBar selectedIds={[...selected]} onClear={() => setSelected(new Set())} onDone={onBulkDone} />
            )}
            <ArtifactTable
              items={data.items}
              sort={state.sort}
              order={state.order}
              onSort={onSort}
              selected={selected}
              onSelect={select}
            />
            <nav aria-label="Pages" className="flex items-center gap-3 text-sm">
              <button
                type="button"
                disabled={state.page <= 1}
                onClick={() => update({ page: state.page - 1 })}
                className="rounded-md border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-700"
              >
                Previous
              </button>
              <span>
                Page {state.page} of {Math.max(1, Math.ceil(total / pageSize))}
              </span>
              <button
                type="button"
                disabled={last >= total}
                onClick={() => update({ page: state.page + 1 })}
                className="rounded-md border border-slate-300 px-2 py-1 disabled:opacity-40 dark:border-slate-700"
              >
                Next
              </button>
            </nav>
          </>
        )}
      </section>
    </div>
  );
}
