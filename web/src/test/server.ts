import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";

import { ARTIFACT_ID, LEADS_NOTICE, artifactDetail, artifactList, custodyReport, evidenceReport, health, jobHistoryItem, searchProviders, settingsResponse } from "./data";

export const API = "/api/v1";

export function apiError(status: number, code: string, message: string) {
  return HttpResponse.json({ error: { code, message, details: {} } }, { status });
}

// Default handlers: an analysed artifact and an empty library. Tests override what they need.
export const server = setupServer(
  http.get(`${API}/artifacts`, () => HttpResponse.json(artifactList([]))),
  http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(artifactDetail())),
  http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () => HttpResponse.json(evidenceReport())),
  http.get(`${API}/artifacts/:artifactId/custody`, () => HttpResponse.json(custodyReport())),
  http.get(`${API}/search/providers`, () => HttpResponse.json(searchProviders())),
  http.get(`${API}/artifacts/:artifactId/external-leads`, ({ params }) =>
    HttpResponse.json({ artifact_id: params.artifactId, notice: LEADS_NOTICE, leads: [] }),
  ),
  http.get(`${API}/health`, () => HttpResponse.json(health())),
  http.get(`${API}/settings`, () => HttpResponse.json(settingsResponse())),
  http.get(`${API}/library/summary`, () =>
    HttpResponse.json({
      artifact_count: 0,
      indexed_count: 0,
      not_indexed_count: 0,
      excluded_count: 0,
      not_indexed: [],
      excluded: [],
      storage: { original_bytes: 0, derived_bytes: 0 },
    }),
  ),
  http.get(`${API}/artifacts/:artifactId/jobs`, ({ params }) =>
    HttpResponse.json({ artifact_id: params.artifactId, jobs: params.artifactId === ARTIFACT_ID ? [jobHistoryItem()] : [] }),
  ),
  http.get(`${API}/artifacts/:artifactId/review-history`, ({ params }) =>
    HttpResponse.json({ artifact_id: params.artifactId, events: [] }),
  ),
);
