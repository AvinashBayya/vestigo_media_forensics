import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useBlocker } from "react-router";

import { ConfirmDialog } from "../ConfirmDialog";

interface ReviewContextValue {
  artifactId: string;
  /** Each review form reports whether it has unsaved changes. */
  setDirty: (key: string, dirty: boolean) => void;
  /** Bumped after any review is saved, so the history reloads. */
  historyVersion: number;
  reviewSaved: () => void;
}

const ReviewContext = createContext<ReviewContextValue | null>(null);

export function useReviewContext(): ReviewContextValue | null {
  return useContext(ReviewContext);
}

/** Reports a form's unsaved state to the page-level guard. */
export function useDirty(key: string, dirty: boolean) {
  const context = useReviewContext();
  const setDirty = context?.setDirty;
  useEffect(() => {
    setDirty?.(key, dirty);
  }, [setDirty, key, dirty]);
  useEffect(() => () => setDirty?.(key, false), [setDirty, key]);
}

/**
 * Review state shared by an artifact page: one unsaved-changes guard for all its review forms (a router
 * supports one blocker at a time), and a history refresh signal.
 */
export function ReviewProvider({ artifactId, children }: { artifactId: string; children: ReactNode }) {
  const [dirtyKeys, setDirtyKeys] = useState<ReadonlySet<string>>(new Set());
  const [historyVersion, setHistoryVersion] = useState(0);
  const dirtyRef = useRef(dirtyKeys);
  dirtyRef.current = dirtyKeys;

  const setDirty = useCallback((key: string, dirty: boolean) => {
    setDirtyKeys((current) => {
      if (current.has(key) === dirty) return current;
      const next = new Set(current);
      if (dirty) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);
  const reviewSaved = useCallback(() => setHistoryVersion((n) => n + 1), []);
  const value = useMemo(
    () => ({ artifactId, setDirty, historyVersion, reviewSaved }),
    [artifactId, setDirty, historyVersion, reviewSaved],
  );

  return (
    <ReviewContext.Provider value={value}>
      {children}
      <UnsavedChangesGuard dirty={dirtyKeys.size > 0} />
    </ReviewContext.Provider>
  );
}

function UnsavedChangesGuard({ dirty }: { dirty: boolean }) {
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);

  useEffect(() => {
    if (!dirty) return;
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  if (blocker.state !== "blocked") return null;
  return (
    <ConfirmDialog
      title="Leave without saving?"
      confirmLabel="Leave without saving"
      cancelLabel="Stay on this page"
      tone="danger"
      onCancel={() => blocker.reset()}
      onConfirm={() => blocker.proceed()}
    >
      <p>You have review changes that have not been saved. They will be lost if you leave.</p>
    </ConfirmDialog>
  );
}
