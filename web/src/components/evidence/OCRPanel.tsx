import type { OCRCandidate, OCRSection, OCRVariant } from "../../api/types";
import { formatPercent, formatValue } from "../../lib/format";
import { Panel } from "../Panel";

const VARIANT_LABELS: Record<OCRVariant, string> = {
  grayscale: "Grayscale pass",
  threshold: "Threshold pass",
};

const TEXT_BOX =
  "max-h-64 overflow-auto rounded-md bg-slate-100 p-3 font-mono text-sm whitespace-pre-wrap dark:bg-slate-800";
const NOTE = "text-xs text-slate-600 dark:text-slate-400";

export function OCRPanel({ section }: { section: OCRSection | null }) {
  return (
    <Panel title="Text in image (OCR)" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <p className="rounded-md bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800">
            <span className="font-medium">Provisional:</span> best-effort automatic OCR, not a verified
            transcription. Text can be missed or misread; check it against the image.
          </p>
          <ExtractedText section={section} />
          <Passes section={section} />
          <Preprocessing section={section} />
        </>
      )}
    </Panel>
  );
}

function ExtractedText({ section }: { section: OCRSection }) {
  if (!section.text) return <p>No text detected.</p>;
  const cleaned = section.cleaned_text;
  return (
    <>
      {cleaned !== null && <p className="text-sm font-medium">Cleaned text</p>}
      <pre className={TEXT_BOX}>{cleaned ?? section.text}</pre>
      {cleaned !== null && (
        <>
          <p className={NOTE}>
            Cleaning: {section.cleaning.map((rule) => `${rule.description} (${rule.lines_affected})`).join(" ")}
          </p>
          <details>
            <summary className="cursor-pointer text-sm">Raw OCR output (unchanged)</summary>
            <pre className={`${TEXT_BOX} mt-2`}>{section.text}</pre>
          </details>
        </>
      )}
      <p className={NOTE}>
        {section.word_count} words · language: {section.languages.join(", ")}
        {section.confidence !== null &&
          ` · Tesseract confidence ${formatPercent(section.confidence)} (the engine's own estimate)`}
      </p>
    </>
  );
}

function Passes({ section }: { section: OCRSection }) {
  if (!section.selected) return null;
  return (
    <div className="space-y-1">
      <p className="text-sm">
        <span className="font-medium">Used: {VARIANT_LABELS[section.selected.variant]}.</span>{" "}
        {section.selected.reason}
      </p>
      <ul className={NOTE}>
        {section.candidates.map((candidate) => (
          <li key={candidate.variant}>{describeCandidate(candidate)}</li>
        ))}
      </ul>
    </div>
  );
}

function describeCandidate(candidate: OCRCandidate): string {
  const label = VARIANT_LABELS[candidate.variant];
  if (candidate.status === "failed") return `${label}: failed (${candidate.error ?? "no detail"})`;
  const confidence =
    candidate.confidence === null ? "no confidence" : `confidence ${formatPercent(candidate.confidence)}`;
  return `${label}: ${candidate.word_count ?? 0} words, ${confidence} (the engine's own estimate)`;
}

function Preprocessing({ section }: { section: OCRSection }) {
  if (section.preprocessing.length === 0) return null;
  return (
    <details>
      <summary className="cursor-pointer text-sm">Preprocessing</summary>
      <ul className="mt-2 space-y-1 text-sm">
        {section.preprocessing.map((step, index) => (
          <li key={`${step.step}-${index}`}>
            <span className={step.applied ? "" : "text-slate-500 dark:text-slate-400"}>{step.description}</span>
            {Object.keys(step.parameters).length > 0 && (
              <span className={`${NOTE} ml-2 font-mono`}>
                {Object.entries(step.parameters)
                  .map(([key, value]) => `${key}=${formatValue(value).replace(/\s+/g, "")}`)
                  .join(" ")}
              </span>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
