import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { AI_LABEL, ARTIFACT_ID, OTHER_ARTIFACT_ID } from "../test/data";
import { renderApp } from "../test/render";
import { API, apiError, server } from "../test/server";

const HIT = {
  artifact_id: ARTIFACT_ID,
  filename: "harbour.jpg",
  media_type: "image",
  source_kind: "analyst_notes",
  source_ref: null,
  score: 0.82,
  text: "Suspected harbour scene, Testville waterfront.",
};

describe("Semantic search page", () => {
  it("explains that it only searches local material, then lists matches", async () => {
    server.use(
      http.get(`${API}/ai/search`, () =>
        HttpResponse.json({ query: "harbour", hits: [HIT], model: "vestigo-local-hash" }),
      ),
    );
    const user = userEvent.setup();
    renderApp("/search");

    const form = await screen.findByRole("form", { name: "Semantic search" });
    expect(form).toHaveTextContent("only what you hold on this machine");
    expect(form).toHaveTextContent("Nothing is sent anywhere");
    expect(form).toHaveTextContent("your own records, not findings");

    await user.type(within(form).getByLabelText(/Words to look for/), "harbour");
    await user.click(within(form).getByRole("button", { name: "Search" }));

    const results = await screen.findByRole("region", { name: /Matches in my material/ });
    expect(results).toHaveTextContent("Indexed with vestigo-local-hash.");
    const list = within(results).getByRole("list", { name: "Search results" });
    expect(within(list).getByRole("link", { name: "harbour.jpg" })).toHaveAttribute(
      "href",
      `/artifacts/${ARTIFACT_ID}`,
    );
    expect(list).toHaveTextContent("my notes · match 0.82");
    expect(list).toHaveTextContent("Testville waterfront");
  });

  it("always shows sources beside an answer, labelled unverified", async () => {
    server.use(
      http.post(`${API}/ai/answer`, () =>
        HttpResponse.json({
          question: "where?",
          sources: [HIT],
          answer: "The notes mention the Testville waterfront [1].",
          notice: AI_LABEL + " This answer was drafted by a local model from the sources listed beside it.",
          label: AI_LABEL,
        }),
      ),
    );
    const user = userEvent.setup();
    renderApp("/search");

    const form = await screen.findByRole("form", { name: "Semantic search" });
    await user.type(within(form).getByLabelText(/Words to look for/), "where?");
    await user.click(within(form).getByRole("button", { name: "Ask a question" }));

    const answer = await screen.findByRole("region", { name: "Answer" });
    expect(answer).toHaveTextContent(AI_LABEL);
    expect(answer).toHaveTextContent("The notes mention the Testville waterfront [1].");
    expect(within(answer).getByRole("heading", { name: "Sources — read these" })).toBeInTheDocument();
    expect(within(answer).getByRole("list", { name: "Answer sources" })).toHaveTextContent("harbour.jpg");
  });

  it("returns the material itself when no model can draft an answer", async () => {
    server.use(
      http.post(`${API}/ai/answer`, () =>
        HttpResponse.json({
          question: "where?",
          sources: [HIT, { ...HIT, artifact_id: OTHER_ARTIFACT_ID, filename: "copy.png" }],
          answer: null,
          notice: "No local text-generation model is available, so Vestigo returned the matching material itself.",
          label: AI_LABEL,
        }),
      ),
    );
    const user = userEvent.setup();
    renderApp("/search");

    const form = await screen.findByRole("form", { name: "Semantic search" });
    await user.type(within(form).getByLabelText(/Words to look for/), "where?");
    await user.click(within(form).getByRole("button", { name: "Ask a question" }));

    const answer = await screen.findByRole("region", { name: "Answer" });
    expect(answer).toHaveTextContent("No local text-generation model is available");
    expect(answer).toHaveTextContent("the matching material is below exactly as you recorded it");
    expect(within(answer).getAllByRole("listitem")).toHaveLength(2);
  });

  it("explains an empty index and surfaces errors", async () => {
    server.use(
      http.get(`${API}/ai/search`, () => HttpResponse.json({ query: "x", hits: [], model: null })),
    );
    const user = userEvent.setup();
    renderApp("/search");

    const form = await screen.findByRole("form", { name: "Semantic search" });
    await user.type(within(form).getByLabelText(/Words to look for/), "x");
    await user.click(within(form).getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/searchable once you index them/)).toBeInTheDocument();

    server.use(
      http.get(`${API}/ai/search`, () => apiError(409, "AI_UNAVAILABLE", "Semantic search is turned off.")),
    );
    await user.click(within(form).getByRole("button", { name: "Search" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Semantic search is turned off.");
  });
});
