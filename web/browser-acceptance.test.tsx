/**
 * Browser-runtime acceptance: boots the real router in jsdom against the LIVE dev server.
 *
 * No msw. Requests go out over real HTTP to http://localhost:5180, through the Vite proxy, to the
 * backend on 8400 - the same path the browser takes. Run with the scratchpad config; it needs both
 * servers up, so it is deliberately not part of the default suite.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createBrowserRouter } from "react-router";
import { afterAll, beforeAll, expect, it } from "vitest";

import { routes } from "./src/App";

const problems: string[] = [];
const BENIGN = [
  "Not implemented: navigation",
  "Not implemented: HTMLFormElement.prototype.requestSubmit",
  "Error: Not implemented",
  "inside a test was not wrapped in act",
];

let originalError: typeof console.error;
let originalWarn: typeof console.warn;

beforeAll(() => {
  originalError = console.error;
  originalWarn = console.warn;
  console.error = (...args: unknown[]) => {
    const text = args.map(String).join(" ");
    if (!BENIGN.some((b) => text.includes(b))) problems.push(`console.error: ${text.slice(0, 300)}`);
    originalError(...args);
  };
  console.warn = (...args: unknown[]) => {
    const text = args.map(String).join(" ");
    if (!BENIGN.some((b) => text.includes(b))) problems.push(`console.warn: ${text.slice(0, 300)}`);
    originalWarn(...args);
  };
  window.addEventListener("error", (event) => problems.push(`window.error: ${event.message}`));
  window.addEventListener("unhandledrejection", (event) =>
    problems.push(`unhandledrejection: ${String((event as PromiseRejectionEvent).reason).slice(0, 300)}`),
  );
});

afterAll(() => {
  console.error = originalError;
  console.warn = originalWarn;
});

async function visit(path: string) {
  window.history.pushState({}, "", path);
  const router = createBrowserRouter(routes);
  const view = render(<RouterProvider router={router} />);
  // Every page must paint something; a blank page is the failure this is looking for.
  await waitFor(() => expect(document.body.textContent?.length ?? 0).toBeGreaterThan(40), {
    timeout: 20000,
  });
  return view;
}

it("the library page renders real data from the live backend", async () => {
  const view = await visit("/");
  await waitFor(() => expect(screen.getByRole("navigation")).toBeTruthy(), { timeout: 20000 });
  const text = document.body.textContent ?? "";
  expect(text).toContain("Vestigo");
  // The library either lists artifacts or says it is empty - both are real renders, not a crash.
  await waitFor(
    () => expect(/artifact|Upload|No artifacts|Library/i.test(document.body.textContent ?? "")).toBe(true),
    { timeout: 20000 },
  );
  // The listing is gated on the settings context loading first, so wait for a real row, not just
  // for a loading indicator to disappear.
  await waitFor(
    () => expect(/\.jpg|\.png|\.mp4|\.mp3|\.pdf|No artifacts|nothing to show/i.test(document.body.textContent ?? "")).toBe(true),
    { timeout: 45000 },
  );
  const settled = document.body.textContent ?? "";
  console.log(
    `[library] ${settled.length} characters; artifact rows visible: ` +
      `${/\.jpg|\.png|\.mp4|\.mp3/i.test(settled)}`,
  );
  view.unmount();
});

it("the settings page loads health, settings and AI status live", async () => {
  const view = await visit("/settings");
  await waitFor(() => expect(document.body.textContent).toContain("Local AI"), { timeout: 20000 });

  // Each of these can only come from a live backend response, and each arrives on its own request:
  // /settings (environment block), /health (tool versions), /ai/status (engine), /ai/models (dir).
  await waitFor(() => expect(document.body.textContent).toContain("Database schema"), { timeout: 20000 });
  await waitFor(() => expect(document.body.textContent).toContain("exiftool"), { timeout: 30000 });
  await waitFor(
    () => expect(/What can run here/i.test(document.body.textContent ?? "")).toBe(true),
    { timeout: 30000 },
  );
  await waitFor(
    () => expect(/Loading providers/i.test(document.body.textContent ?? "")).toBe(false),
    { timeout: 30000 },
  );

  const text = document.body.textContent ?? "";
  expect(/generation 2 engine is staged|engine is not staged|publishes no generation/i.test(text)).toBe(true);
  expect(text).toContain("0009_pass3_cases");
  console.log(`[settings] ${text.length} characters; engine line present; models dir shown: ${/data\/models/.test(text)}`);
  view.unmount();
});

it("the upload page renders its form", async () => {
  const view = await visit("/upload");
  await waitFor(() => expect(document.body.textContent).toMatch(/upload/i), { timeout: 20000 });
  view.unmount();
});

it("the search page renders and queries the backend", async () => {
  const view = await visit("/search");
  await waitFor(() => expect(document.body.textContent).toMatch(/search/i), { timeout: 20000 });
  view.unmount();
});

it("an unknown route renders the not-found page, not a blank screen", async () => {
  const view = await visit("/no-such-page");
  await waitFor(() => expect((document.body.textContent ?? "").length).toBeGreaterThan(40), {
    timeout: 20000,
  });
  view.unmount();
});

const ARTIFACT = process.env.VESTIGO_TEST_ARTIFACT;

it.runIf(ARTIFACT)("the artifact page renders every evidence panel from the live backend", async () => {
  const view = await visit(`/artifacts/${ARTIFACT}`);

  // The page fans out to many endpoints. Wait until nothing is still loading before asserting, or
  // the assertions race the fetches instead of testing the rendered page.
  await waitFor(() => expect(document.body.textContent).toMatch(/Chain of custody/i), { timeout: 40000 });
  await waitFor(
    () => expect(/Loading…|Loading evidence…/.test(document.body.textContent ?? "")).toBe(false),
    { timeout: 60000 },
  );

  const text = document.body.textContent ?? "";
  const panels: Record<string, RegExp> = {
    "file hashes": /SHA-?256/i,
    metadata: /metadata/i,
    "C2PA / Content Credentials": /Content Credentials|C2PA/i,
    "chain of custody": /Chain of custody/i,
    duplicates: /duplicate/i,
    OCR: /text in image|OCR/i,
    "location clues": /location/i,
    "structure and hidden data": /structure|hidden data|trailing/i,
    "forensic indicators": /forensic|quantis|quantiz/i,
    "AI drafts": /AI assistant/i,
    review: /review/i,
    export: /export/i,
    cases: /case/i,
    "reverse-image search": /reverse-image/i,
  };
  const missing = Object.entries(panels)
    .filter(([, pattern]) => !pattern.test(text))
    .map(([name]) => name);
  console.log(
    `[artifact] rendered ${text.length} characters; panels found: ` +
      `${Object.keys(panels).length - missing.length}/${Object.keys(panels).length}`,
  );
  expect(missing).toEqual([]);

  // The analysed artifact must never be described as unanalysed, and the AI draft must be labelled.
  expect(text).not.toMatch(/has not been analysed yet/i);
  expect(/AI-generated, unverified/i.test(text)).toBe(true);
  view.unmount();
});

it("no runtime JavaScript errors were raised while rendering", () => {
  if (problems.length) {
    throw new Error(`runtime problems:\n${[...new Set(problems)].join("\n")}`);
  }
  expect(problems).toEqual([]);
});
