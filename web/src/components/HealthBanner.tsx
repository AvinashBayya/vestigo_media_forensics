import { useEffect, useState } from "react";

import { ApiError, getHealth } from "../api/client";
import type { HealthResponse } from "../api/types";

const CONSEQUENCES: Record<string, string> = {
  exiftool: "metadata and C2PA detection will be recorded as failed",
  tesseract: "OCR will be recorded as failed",
};

/**
 * Warns when the backend, its database or storage, or a Milestone 1-2 tool is unavailable, so failed
 * checks are explained before an analysis runs. Video tools (used from Milestone 3) are not mentioned.
 */
export function HealthBanner() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    let current = true;
    getHealth()
      .then((result) => current && setHealth(result))
      .catch((err: unknown) => current && setUnreachable(err instanceof ApiError && err.code === "NETWORK_ERROR"));
    return () => {
      current = false;
    };
  }, []);

  const problems: string[] = [];
  if (unreachable) problems.push("The Vestigo backend cannot be reached. Check that it is running on port 8400.");
  if (health?.database === "error") problems.push("The database is unavailable or at the wrong schema version.");
  if (health?.storage === "error") problems.push("The data folder is unavailable.");
  for (const [name, tool] of Object.entries(health?.tools ?? {})) {
    if (tool.status !== "ok" && CONSEQUENCES[name]) {
      problems.push(`${name} is ${tool.status === "missing" ? "not installed" : "not working"}: ${CONSEQUENCES[name]}.`);
    }
  }
  if (problems.length === 0) return null;

  return (
    <div role="alert" aria-label="Service status" className="border-b border-amber-300 bg-amber-50 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
      <ul className="mx-auto max-w-6xl list-disc space-y-1 px-8 py-2">
        {problems.map((problem) => (
          <li key={problem}>{problem}</li>
        ))}
      </ul>
    </div>
  );
}
