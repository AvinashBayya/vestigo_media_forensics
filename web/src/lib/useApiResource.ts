import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";

export interface ApiResource<T> {
  data: T | null;
  error: ApiError | null;
  /** True while a request is in flight, including reloads that keep the previous data. */
  loading: boolean;
  reload: () => void;
}

/**
 * Loads data and tracks loading, error, and retry in one place. A newer request always wins, so a slow
 * response for an old query never replaces the result of a newer one.
 */
export function useApiResource<T>(load: () => Promise<T>, key: string): ApiResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);
    loadRef
      .current()
      .then((result) => {
        if (current) setData(result);
      })
      .catch((err: unknown) => {
        if (current) setError(err instanceof ApiError ? err : new ApiError("UNKNOWN_ERROR", String(err), 0));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [key, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { data, error, loading, reload };
}
