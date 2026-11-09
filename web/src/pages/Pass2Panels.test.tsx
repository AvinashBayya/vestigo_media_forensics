import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import {
  ARTIFACT_ID,
  documentDetail,
  documentReport,
  evidenceReport,
  forensicIndicators,
  structuralSection,
} from "../test/data";
import { renderApp } from "../test/render";
import { API, server } from "../test/server";

const PAGE = `/artifacts/${ARTIFACT_ID}`;

describe("Structure and hidden-data panel", () => {
  it("refuses to call a file clean when it finds nothing", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(evidenceReport({ structural: structuralSection() })),
      ),
    );
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Structure and hidden-data checks" });
    expect(panel).toHaveTextContent("Nothing structurally unusual was found");
    expect(panel).toHaveTextContent("not a finding that the file is clean");
    expect(panel).toHaveTextContent("undetectable by these checks");
    // Measurements are shown with their method either way.
    const measurements = within(panel).getByRole("list", { name: "Byte measurements" });
    expect(measurements).toHaveTextContent("byte_entropy");
    expect(measurements).toHaveTextContent("Shannon entropy over all file bytes");
  });

  it("places each finding with its offset and size", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            structural: structuralSection({
              container: "png",
              file_size: 9871,
              logical_end: 9726,
              trailing_bytes: 145,
              findings: [
                {
                  kind: "trailing_data",
                  offset: 9726,
                  size: 145,
                  detail: "145 bytes follow the end of the png data at offset 9726.",
                },
                {
                  kind: "embedded_signature",
                  offset: 9726,
                  size: 4,
                  detail: "zip_entry signature bytes at offset 9726.",
                },
              ],
            }),
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Structure and hidden-data checks" });
    const findings = within(panel).getByRole("list", { name: "Structural findings" });
    expect(findings).toHaveTextContent("Data after the end of the format");
    expect(findings).toHaveTextContent("offset 9,726");
    expect(findings).toHaveTextContent("File signature inside the file");
    expect(findings).toHaveTextContent("zip_entry signature bytes");
    // Framed as somewhere to look, not a conclusion.
    expect(panel).toHaveTextContent("a place to look rather than a conclusion");
  });
});

describe("Forensic indicators panel", () => {
  it("shows measurements with the no-threshold caveat", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(evidenceReport({ forensic_indicators: forensicIndicators() })),
      ),
    );
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Forensic indicators" });
    expect(panel).toHaveTextContent('no threshold separates "edited" from "original"');
    const tables = within(panel).getByRole("list", { name: "Quantisation tables" });
    expect(tables).toHaveTextContent("implies quality 92 for the last save");
    expect(panel).toHaveTextContent("Decoded 640×480");
    expect(within(panel).getByRole("list", { name: "Channel statistics" })).toHaveTextContent("red");
  });

  it("reports a dimension mismatch as a fact with its ordinary causes", async () => {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () =>
        HttpResponse.json(
          evidenceReport({
            forensic_indicators: forensicIndicators({
              declared_width: 800,
              declared_height: 600,
              dimensions_match: false,
            }),
          }),
        ),
      ),
    );
    renderApp(PAGE);

    const panel = await screen.findByRole("region", { name: "Forensic indicators" });
    expect(panel).toHaveTextContent("metadata declares 800×600");
    expect(panel).toHaveTextContent("Declared and decoded dimensions differ");
    expect(panel).toHaveTextContent("cropping tools, resizers, and metadata editors all cause this");
  });
});

describe("Document artifact page", () => {
  function serveDocument(report = documentReport()) {
    server.use(
      http.get(`${API}/artifacts/${ARTIFACT_ID}`, () => HttpResponse.json(documentDetail())),
      http.get(`${API}/artifacts/${ARTIFACT_ID}/evidence`, () => HttpResponse.json(report)),
    );
  }

  it("shows structure, provisional text, and embedded images", async () => {
    serveDocument();
    renderApp(PAGE);

    expect(await screen.findByRole("heading", { name: "report.pdf" })).toBeInTheDocument();

    const structure = await screen.findByRole("region", { name: "Document structure" });
    expect(structure).toHaveTextContent("PDF version");
    expect(structure).toHaveTextContent("1.7");
    expect(structure).toHaveTextContent("Pages declared");

    const text = screen.getByRole("region", { name: "Text in document" });
    expect(text).toHaveTextContent("Provisional:");
    expect(text).toHaveTextContent("without font mapping");
    expect(text).toHaveTextContent("Vestigo fixture document");
    expect(text).toHaveTextContent("2 non-text stream(s) skipped");

    const images = screen.getByRole("region", { name: "Images embedded in the document" });
    const thumbnails = within(images).getAllByRole("img");
    expect(thumbnails[0]).toHaveAttribute(
      "src",
      `/api/v1/artifacts/${ARTIFACT_ID}/derived/df_${"5".repeat(32)}/content`,
    );
    expect(images).toHaveTextContent("not rendered pages");

    // Image and video panels do not apply to a document.
    expect(screen.queryByRole("region", { name: "Forensic indicators" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Perceptual hash" })).not.toBeInTheDocument();
  });

  it("states that signatures are present but never validated", async () => {
    const report = documentReport();
    serveDocument({
      ...report,
      pdf_structure: { ...report.pdf_structure!, signature_count: 1, eof_markers: 2, incremental_updates: 1 },
    });
    renderApp(PAGE);

    const structure = await screen.findByRole("region", { name: "Document structure" });
    expect(structure).toHaveTextContent("contains 1 signature structure");
    expect(structure).toHaveTextContent("Vestigo does not validate PDF signatures");
    // A second save is explained rather than flagged.
    expect(structure).toHaveTextContent("The file was saved 2 times");
    expect(structure).toHaveTextContent("not a sign of tampering");
  });

  it("explains an empty text result instead of implying blank pages", async () => {
    const report = documentReport();
    serveDocument({
      ...report,
      pdf_text: {
        ...report.pdf_text!,
        text: "",
        character_count: 0,
        streams_read: 0,
        notes: ["No text operators were readable. This does not mean the pages are blank."],
      },
      pdf_images: { ...report.pdf_images!, images: [], extracted: 0 },
    });
    renderApp(PAGE);

    const text = await screen.findByRole("region", { name: "Text in document" });
    expect(text).toHaveTextContent("does not");
    expect(text).toHaveTextContent("mean the pages are blank");
    const images = screen.getByRole("region", { name: "Images embedded in the document" });
    expect(images).toHaveTextContent("No JPEG-compressed images were extracted");
  });

  it("lists document features as presence counts without implying wrongdoing", async () => {
    const report = documentReport();
    serveDocument({
      ...report,
      pdf_structure: {
        ...report.pdf_structure!,
        markers: { javascript: 1, open_action: 1, interactive_form: 2 },
      },
    });
    renderApp(PAGE);

    const structure = await screen.findByRole("region", { name: "Document structure" });
    const features = within(structure).getByRole("list", { name: "Document features" });
    expect(features).toHaveTextContent("JavaScript ×1");
    expect(features).toHaveTextContent("Automatic action on open ×1");
    expect(features).toHaveTextContent("Interactive form ×2");
    expect(structure).toHaveTextContent("none of these is a finding of wrongdoing");
  });
});
