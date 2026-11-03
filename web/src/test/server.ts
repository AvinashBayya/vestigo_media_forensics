import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";

import { ARTIFACT_ID, artifactDetail, artifactList, evidenceReport } from "./data";

export const API = "/api/v1";

export function apiError(status: number, code: string, message: string) {
  return HttpResponse.json({ error: { code, message, details: {} } }, { status });
}

// Default handlers: an analysed artifact and an empty library. Tests override what they need.
export const server = setupServer(
  http.get(`${API}/artifacts`, () => HttpResponse.json(artifactList([]))),
  http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(artifactDetail())),
  http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () => HttpResponse.json(evidenceReport())),
);
