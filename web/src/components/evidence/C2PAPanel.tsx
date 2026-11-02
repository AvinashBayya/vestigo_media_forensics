import type { C2PAManifest, C2PASection } from "../../api/types";
import { formatValue } from "../../lib/format";
import { Panel } from "../Panel";

const CLAIM_FIELDS = ["Claim_generator", "Title", "Format", "InstanceID"];

export function C2PAPanel({ section }: { section: C2PASection | null }) {
  const detectors = section?.details.detectors;
  return (
    <Panel title="Content Credentials (C2PA)" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <p className="font-medium">
            {section.present
              ? "A Content Credentials (C2PA) manifest was found in the file."
              : "No Content Credentials (C2PA) manifest was found in the file."}
          </p>
          <p className="text-slate-600 dark:text-slate-400">
            Detection only: signatures, certificates, and hash bindings are not validated in this version, so a
            manifest is not proof that the content is authentic or that its claims are true. Most images have no
            manifest, so its absence proves nothing.
          </p>
          {detectors && (
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Byte-level check: {detectors.byte_scan?.found ? "found" : "not found"} · ExifTool:{" "}
              {detectors.exiftool?.found ? "found" : "not found"}
            </p>
          )}
          {section.details.manifests?.map((manifest, index) => (
            <ManifestSummary
              key={manifest.label ?? index}
              manifest={manifest}
              active={manifest.label === section.details.active_manifest_label}
            />
          ))}
        </>
      )}
    </Panel>
  );
}

function ManifestSummary({ manifest, active }: { manifest: C2PAManifest; active: boolean }) {
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <p className="font-mono text-xs break-all">
        {manifest.label}
        {active && <span className="ml-2 font-sans text-slate-500">(last in store)</span>}
      </p>
      <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
        {CLAIM_FIELDS.filter((field) => field in manifest.claim).map((field) => (
          <div key={field} className="contents">
            <dt className="font-medium">{field.replace("_", " ")}</dt>
            <dd className="break-all">{formatValue(manifest.claim[field])}</dd>
          </div>
        ))}
        <dt className="font-medium">Signature box</dt>
        <dd>{manifest.signature_present ? "present (not checked)" : "not present"}</dd>
      </dl>
      {manifest.assertions.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1">
          {manifest.assertions.map((assertion) => (
            <li key={assertion} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs dark:bg-slate-800">
              {assertion}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
