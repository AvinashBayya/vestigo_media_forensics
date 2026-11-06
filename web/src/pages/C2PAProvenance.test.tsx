import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { C2PAManifestInfo, C2PASection } from "../api/types";
import { ARTIFACT_ID, VALIDATOR, artifactDetail, c2paSection, evidenceReport, videoDetail, videoReport } from "../test/data";
import { renderApp } from "../test/render";
import { API, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

function manifestInfo(overrides: Partial<C2PAManifestInfo> = {}): C2PAManifestInfo {
  return {
    label: "urn:c2pa:0a1b2c3d-0000-0000-0000-000000000001",
    title: "signed.jpg",
    claim_generator: "Vestigo Test Signer/1.0",
    signature_issuer: "Vestigo Test CA",
    signature_common_name: "Vestigo Test Signer",
    signature_cert_serial: "12345",
    signature_time: "2026-11-05T10:00:00+00:00",
    signature_algorithm: "Es256",
    assertion_labels: ["c2pa.actions", "c2pa.hash.data"],
    ingredient_count: 0,
    ...overrides,
  };
}

function validSection(overrides: Partial<C2PASection> = {}): C2PASection {
  return c2paSection({
    present: true,
    status: "valid",
    validation_state: "Valid",
    manifest_count: 1,
    active_manifest: manifestInfo().label,
    manifests: [manifestInfo()],
    validation_codes: {
      success: [{ code: "claimSignature.validated", explanation: "claim signature valid" }],
      informational: [],
      failure: [{ code: "signingCredential.untrusted", explanation: "signing credential found on untrusted list" }],
    },
    ...overrides,
  });
}

function serveImage(c2pa: C2PASection) {
  server.use(
    http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () => HttpResponse.json(evidenceReport({ c2pa }))),
  );
}

async function findPanel() {
  return await screen.findByRole("region", { name: "Content Credentials (C2PA)" });
}

describe("C2PA provenance panel", () => {
  it("shows a valid manifest with signer details and the honesty caveats", async () => {
    serveImage(validSection());
    renderApp(PAGE);

    const panel = await findPanel();
    expect(within(panel).getByText("Valid")).toBeInTheDocument();
    expect(panel).toHaveTextContent("hashes and claim signature verify for the data they cover");
    // Valid never means truthful, and no trust list means the signer stays unestablished.
    expect(panel).toHaveTextContent("not proof that the content is truthful, accurate, or unmanipulated");
    expect(panel).toHaveTextContent("signer's identity and trustworthiness are not established");
    // The no-trust-list failure code is surfaced, never hidden.
    expect(within(panel).getByText("signingCredential.untrusted")).toBeInTheDocument();

    expect(panel).toHaveTextContent("1 manifest in the store · validator state: Valid");
    expect(panel).toHaveTextContent("(active manifest)");
    expect(within(panel).getByText("Vestigo Test Signer/1.0")).toBeInTheDocument();
    expect(within(panel).getByText("Vestigo Test Signer")).toBeInTheDocument();
    expect(within(panel).getByText("Vestigo Test CA")).toBeInTheDocument();
    expect(within(panel).getByText("c2pa.actions")).toBeInTheDocument();
    expect(panel).toHaveTextContent("recorded as written, not verified against any registry");
    expect(panel).toHaveTextContent(`Validated locally with ${VALIDATOR}. No network access was used.`);
  });

  it("shows an invalid manifest with its recorded failure codes", async () => {
    serveImage(
      validSection({
        status: "invalid",
        validation_state: "Invalid",
        validation_codes: {
          success: [],
          informational: [],
          failure: [
            { code: "assertion.dataHash.mismatch", explanation: "hash does not match" },
            { code: "signingCredential.untrusted", explanation: null },
          ],
        },
      }),
    );
    renderApp(PAGE);

    const panel = await findPanel();
    expect(within(panel).getByText("Invalid")).toBeInTheDocument();
    expect(panel).toHaveTextContent("present, but it does not validate");
    expect(panel).toHaveTextContent("not necessarily deliberate tampering");
    expect(within(panel).getByText("assertion.dataHash.mismatch")).toBeInTheDocument();
    expect(within(panel).getByText("hash does not match")).toBeInTheDocument();
  });

  it("shows detected-but-unverifiable data with the validator's error", async () => {
    serveImage(
      c2paSection({
        present: true,
        status: "unverifiable",
        validator_error: "unsupported format: C2paError.NotSupported",
      }),
    );
    renderApp(PAGE);

    const panel = await findPanel();
    expect(within(panel).getByText("Unverifiable")).toBeInTheDocument();
    expect(panel).toHaveTextContent("could not be validated");
    expect(panel).toHaveTextContent("nothing was checked");
    expect(panel).toHaveTextContent("Validator: unsupported format: C2paError.NotSupported");
  });

  it("explains that absence proves nothing", async () => {
    serveImage(c2paSection());
    renderApp(PAGE);

    const panel = await findPanel();
    expect(within(panel).getByText("Absent")).toBeInTheDocument();
    expect(panel).toHaveTextContent("No Content Credentials (C2PA) data was found in the file.");
    expect(panel).toHaveTextContent("Absence does not mean the file is fake, edited, or untrustworthy.");
    expect(within(panel).queryByText("Valid")).not.toBeInTheDocument();
  });

  it("validates Content Credentials on video artifacts", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(videoDetail())),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(videoReport({ c2pa: validSection({ details: {} }) })),
      ),
    );
    renderApp(PAGE);

    const panel = await findPanel();
    expect(within(panel).getByText("Valid")).toBeInTheDocument();
    expect(within(panel).getByText("Vestigo Test Signer/1.0")).toBeInTheDocument();
  });

  it("validates Content Credentials on audio artifacts", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () =>
        HttpResponse.json(
          artifactDetail({ filename: "tone.wav", media_type: "audio", mime_type: "audio/wav", duration_seconds: 2 }),
        ),
      ),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({ c2pa: c2paSection({ details: {} }), ocr: null, perceptual_hash: null }),
        ),
      ),
    );
    renderApp(PAGE);

    const panel = await findPanel();
    expect(within(panel).getByText("Absent")).toBeInTheDocument();
    expect(panel).toHaveTextContent("many platforms strip them");
  });
});
