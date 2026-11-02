import type { OCRSection } from "../../api/types";
import { formatPercent } from "../../lib/format";
import { Panel } from "../Panel";

export function OCRPanel({ section }: { section: OCRSection | null }) {
  return (
    <Panel title="Text in image (OCR)" provenance={section?.provenance ?? null}>
      {section &&
        (section.text ? (
          <>
            <pre className="max-h-64 overflow-auto rounded-md bg-slate-100 p-3 font-mono text-sm whitespace-pre-wrap dark:bg-slate-800">
              {section.text}
            </pre>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              {section.word_count} words · language: {section.languages.join(", ")}
              {section.confidence !== null &&
                ` · Tesseract confidence ${formatPercent(section.confidence)} (the engine's own estimate)`}
            </p>
          </>
        ) : (
          <p>No text detected.</p>
        ))}
    </Panel>
  );
}
