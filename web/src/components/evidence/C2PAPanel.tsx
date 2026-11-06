import type { C2PAManifest, C2PAManifestInfo, C2PASection, C2PAStatus } from "../../api/types";
import { formatValue } from "../../lib/format";
import { Panel } from "../Panel";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

const STATUS_HEADLINE: Record<C2PAStatus, string> = {
  valid:
    "Content Credentials (C2PA) data is present and its hashes and claim signature verify for the data they cover.",
  invalid: "Content Credentials (C2PA) data is present, but it does not validate.",
  unverifiable: "Content Credentials (C2PA) data could not be validated.",
  absent: "No Content Credentials (C2PA) data was found in the file.",
};

const STATUS_BADGE: Record<C2PAStatus, { label: string; className: string }> = {
  valid: {
    label: "Valid",
    className: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100",
  },
  invalid: { label: "Invalid", className: "bg-rose-100 text-rose-900 dark:bg-rose-900 dark:text-rose-100" },
  unverifiable: {
    label: "Unverifiable",
    className: "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100",
  },
  absent: { label: "Absent", className: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200" },
};

const STATUS_CAVEAT: Record<C2PAStatus, string> = {
  valid:
    "A valid manifest is not proof that the content is truthful, accurate, or unmanipulated — only that " +
    "the covered data has not changed since signing. No trust list is configured, so the signer's " +
    "identity and trustworthiness are not established.",
  invalid:
    "An invalid result shows the recorded reason. It can stem from re-encoding, truncation, or other " +
    "processing after signing — not necessarily deliberate tampering.",
  unverifiable:
    "The validator could not read this file's C2PA data, so nothing was checked. This says nothing " +
    "about the content itself.",
  absent:
    "Most media has no Content Credentials, and many platforms strip them. Absence does not mean the " +
    "file is fake, edited, or untrustworthy.",
};

export function C2PAPanel({ section }: { section: C2PASection | null }) {
  return (
    <Panel title="Content Credentials (C2PA)" provenance={section?.provenance ?? null}>
      {section && (section.validation_performed ? <ValidationView section={section} /> : <DetectionOnlyView section={section} />)}
    </Panel>
  );
}

function ValidationView({ section }: { section: C2PASection }) {
  const status = section.status ?? "unverifiable";
  const badge = STATUS_BADGE[status];
  const failures = section.validation_codes?.failure ?? [];
  const detectors = section.details.detectors;
  return (
    <>
      <p className="flex items-start gap-2">
        <span className={`mt-0.5 rounded px-1.5 py-0.5 text-xs font-semibold ${badge.className}`}>{badge.label}</span>
        <span className="font-medium">{STATUS_HEADLINE[status]}</span>
      </p>
      <p className="text-slate-600 dark:text-slate-400">{STATUS_CAVEAT[status]}</p>
      {section.validator_error && (
        <p className="text-sm text-rose-800 dark:text-rose-300">Validator: {section.validator_error}</p>
      )}
      {failures.length > 0 && (
        <div>
          <p className="text-sm font-medium">Validation failures reported:</p>
          <ul className="mt-1 space-y-1">
            {failures.map((failure, index) => (
              <li key={failure.code ?? index} className="text-sm">
                <span className="rounded bg-rose-100 px-1.5 py-0.5 font-mono text-xs text-rose-900 dark:bg-rose-900 dark:text-rose-100">
                  {failure.code ?? "unknown"}
                </span>
                {failure.explanation && <span className="ml-2">{failure.explanation}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(section.manifest_count ?? 0) > 0 && (
        <p className={MUTED}>
          {section.manifest_count} {section.manifest_count === 1 ? "manifest" : "manifests"} in the store
          {section.validation_state && ` · validator state: ${section.validation_state}`}
        </p>
      )}
      {section.manifests.map((manifest) => (
        <ManifestCard key={manifest.label} manifest={manifest} active={manifest.label === section.active_manifest} />
      ))}
      {detectors && (
        <p className={MUTED}>
          Byte-level check: {detectors.byte_scan?.found ? "found" : "not found"} · ExifTool:{" "}
          {detectors.exiftool?.found ? "found" : "not found"}
        </p>
      )}
      {section.validator && <p className={MUTED}>Validated locally with {section.validator}. No network access was used.</p>}
    </>
  );
}

function Row({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="contents">
      <dt className="font-medium">{label}</dt>
      <dd className="break-all">{value}</dd>
    </div>
  );
}

function ManifestCard({ manifest, active }: { manifest: C2PAManifestInfo; active: boolean }) {
  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <p className="font-mono text-xs break-all">
        {manifest.label}
        {active && <span className="ml-2 font-sans text-slate-500">(active manifest)</span>}
      </p>
      <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
        <Row label="Title" value={manifest.title} />
        <Row label="Claim generator" value={manifest.claim_generator} />
        <Row label="Signed by" value={manifest.signature_common_name} />
        <Row label="Certificate issuer" value={manifest.signature_issuer} />
        <Row label="Signature time" value={manifest.signature_time} />
        <Row label="Signature algorithm" value={manifest.signature_algorithm} />
        <Row label="Certificate serial" value={manifest.signature_cert_serial} />
        {manifest.ingredient_count > 0 && (
          <Row
            label="Ingredients"
            value={`${manifest.ingredient_count} (earlier ${manifest.ingredient_count === 1 ? "version" : "versions"} referenced by this manifest)`}
          />
        )}
      </dl>
      {manifest.assertion_labels.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1" aria-label={`Assertions in ${manifest.label}`}>
          {manifest.assertion_labels.map((assertion) => (
            <li key={assertion} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs dark:bg-slate-800">
              {assertion}
            </li>
          ))}
        </ul>
      )}
      <p className={`mt-2 ${MUTED}`}>
        Names above are what the manifest and its certificate claim; they are recorded as written, not verified
        against any registry.
      </p>
    </div>
  );
}

/** Records analysed before Milestone 4: C2PA data was detected but never validated. */
function DetectionOnlyView({ section }: { section: C2PASection }) {
  const detectors = section.details.detectors;
  return (
    <>
      <p className="font-medium">
        {section.present
          ? "A Content Credentials (C2PA) manifest was found in the file."
          : "No Content Credentials (C2PA) manifest was found in the file."}
      </p>
      <p className="text-slate-600 dark:text-slate-400">
        Detection only: signatures, certificates, and hash bindings were not validated when this record was
        made, so a manifest is not proof that the content is authentic or that its claims are true. Most
        images have no manifest, so its absence proves nothing. Run the analysis again to validate the
        manifest with the current version.
      </p>
      {detectors && (
        <p className={MUTED}>
          Byte-level check: {detectors.byte_scan?.found ? "found" : "not found"} · ExifTool:{" "}
          {detectors.exiftool?.found ? "found" : "not found"}
        </p>
      )}
      {section.details.manifests?.map((manifest, index) => (
        <DetectedManifest
          key={manifest.label ?? index}
          manifest={manifest}
          active={manifest.label === section.details.active_manifest_label}
        />
      ))}
    </>
  );
}

const CLAIM_FIELDS = ["Claim_generator", "Title", "Format", "InstanceID"];

function DetectedManifest({ manifest, active }: { manifest: C2PAManifest; active: boolean }) {
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
