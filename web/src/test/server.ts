import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";

import { ARTIFACT_ID, CASES_NOTICE, DRAFTS_NOTICE, LEADS_NOTICE, LOCATION_NOTICE, TRANSCRIPTS_NOTICE, aiStatus, artifactDetail, artifactList, custodyReport, evidenceReport, health, jobHistoryItem, searchProviders, settingsResponse } from "./data";

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
  http.get(`${API}/artifacts/:artifactId/location-candidates`, ({ params }) =>
    HttpResponse.json({ artifact_id: params.artifactId, notice: LOCATION_NOTICE, candidates: [] }),
  ),
  http.get(`${API}/ai/status`, () => HttpResponse.json(aiStatus())),
  http.get(`${API}/cases`, () => HttpResponse.json({ notice: CASES_NOTICE, cases: [] })),
  http.get(`${API}/geo/artifacts/:artifactId/tools`, ({ params }) =>
    HttpResponse.json({
      artifact_id: params.artifactId,
      notice: "Coordinate conversions and distances between points Vestigo already holds.",
      points: [],
      pairs: [],
      limitations: [],
      offline_map_available: false,
      offline_map_path: null,
    }),
  ),
  http.get(`${API}/ai/artifacts/:artifactId/drafts`, ({ params }) =>
    HttpResponse.json({
      artifact_id: params.artifactId,
      notice: DRAFTS_NOTICE,
      label: "AI-generated, unverified - analyst must review.",
      drafts: [],
    }),
  ),
  http.get(`${API}/ai/artifacts/:artifactId/transcripts`, ({ params }) =>
    HttpResponse.json({ artifact_id: params.artifactId, notice: TRANSCRIPTS_NOTICE, transcripts: [] }),
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
