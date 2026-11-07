import { useCallback, useEffect, useState, type FormEvent } from "react";

import {
  createLocationCandidate,
  deleteLocationCandidate,
  errorMessage,
  listLocationCandidates,
  openStreetMapUrl,
  updateLocationCandidate,
} from "../../api/client";
import type {
  AnalystAssessment,
  LocationCandidate,
  LocationCandidatesResponse,
  LocationCluesSection,
  LocationCoordinate,
  LocationTag,
  ReviewState,
  SupportRef,
  SupportType,
} from "../../api/types";
import { REVIEW_STATES } from "../../api/types";
import { REVIEW_LABELS, formatDateTime } from "../../lib/format";
import { useSettings } from "../../lib/settings";
import { Panel, sectionAnchor } from "../Panel";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";
const INPUT =
  "w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-900";
const BUTTON = "rounded-md border border-slate-300 px-2 py-1 text-sm font-medium dark:border-slate-600";

const ASSESSMENTS: AnalystAssessment[] = ["speculative", "possible", "likely"];
const SUPPORT_LABELS: Record<SupportType, string> = {
  evidence_record: "evidence record",
  derived_file: "derived file",
  external_lead: "external lead",
};

/** Clicking the map link sends the coordinates to openstreetmap.org — said plainly, before the click. */
const MAP_WARNING =
  "Opening the map sends these coordinates to openstreetmap.org in the link itself. Vestigo sends " +
  "nothing on its own and cannot see what happens on that site.";

function TagList({ label, tags }: { label: string; tags: LocationTag[] }) {
  if (tags.length === 0) return null;
  return (
    <div>
      <h3 className="font-medium">{label}</h3>
      <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
        {tags.map((tag) => (
          <div key={`${tag.tag}:${tag.value}`} className="contents">
            <dt className={`font-mono ${MUTED}`}>{tag.tag}</dt>
            <dd className="break-words">{tag.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function CoordinateRow({ coordinate, mapEnabled }: { coordinate: LocationCoordinate; mapEnabled: boolean }) {
  const usable = coordinate.valid && coordinate.latitude !== null && coordinate.longitude !== null;
  return (
    <li className="space-y-1">
      <p className="flex flex-wrap items-baseline gap-2">
        <span className={MUTED}>{coordinate.source}</span>
        {usable ? (
          <span className="font-mono">
            {coordinate.latitude}, {coordinate.longitude}
          </span>
        ) : (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-900 dark:bg-amber-900 dark:text-amber-100">
            Unusable value
          </span>
        )}
      </p>
      {(coordinate.latitude_as_written || coordinate.longitude_as_written) && (
        <p className={MUTED}>
          As written: <span className="font-mono">{coordinate.latitude_as_written ?? "—"}</span>
          {" · "}
          <span className="font-mono">{coordinate.longitude_as_written ?? "—"}</span>
        </p>
      )}
      {coordinate.problem && (
        <p className="text-sm text-amber-900 dark:text-amber-200">
          {coordinate.problem} — the value is kept exactly as written.
        </p>
      )}
      {usable && mapEnabled && (
        <p className="space-x-2">
          <a
            href={openStreetMapUrl(coordinate.latitude!, coordinate.longitude!)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium underline"
          >
            Open in OpenStreetMap (external)
          </a>
          <span className={MUTED}>{MAP_WARNING}</span>
        </p>
      )}
    </li>
  );
}

interface LocationPanelProps {
  artifactId: string;
  section: LocationCluesSection | null;
  /** Called after a candidate is recorded, edited, or deleted, so custody can refresh. */
  onCandidatesChanged?: () => void;
}

export function LocationPanel({ artifactId, section, onCandidatesChanged }: LocationPanelProps) {
  const { settings } = useSettings();
  const mapEnabled = settings.enable_external_map_links;
  const [candidates, setCandidates] = useState<LocationCandidatesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setCandidates(await listLocationCandidates(artifactId));
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [artifactId]);

  useEffect(() => {
    void load();
  }, [load]);

  function changed() {
    void load();
    onCandidatesChanged?.();
  }

  const nothingFound =
    section !== null &&
    section.coordinates.length === 0 &&
    section.text_clues.length === 0 &&
    section.altitude_meters === null;

  return (
    <Panel title="Location clues" provenance={section?.provenance ?? null}>
      {section && (
        <>
          {nothingFound ? (
            <p>
              No location metadata was found. Absence proves nothing: most cameras have GPS off and
              most platforms strip it on upload.
            </p>
          ) : (
            <>
              {section.coordinates.length > 0 && (
                <div>
                  <h3 className="font-medium">Coordinates</h3>
                  <ul aria-label="Coordinates" className="mt-1 space-y-2">
                    {section.coordinates.map((coordinate, index) => (
                      <CoordinateRow
                        key={`${coordinate.source}-${index}`}
                        coordinate={coordinate}
                        mapEnabled={mapEnabled}
                      />
                    ))}
                  </ul>
                  {!mapEnabled && (
                    <p className={`mt-1 ${MUTED}`}>
                      External map links are off. Turn them on in Settings to open coordinates in
                      OpenStreetMap; doing so sends them to that service.
                    </p>
                  )}
                </div>
              )}
              {section.altitude_meters !== null && (
                <p className="text-sm">
                  <span className="font-medium">Altitude:</span> {section.altitude_meters} m
                  {section.altitude_reference && ` (${section.altitude_reference})`}
                  {section.altitude_as_written && (
                    <span className={MUTED}> · as written: {section.altitude_as_written}</span>
                  )}
                </p>
              )}
              <TagList label="Place names in metadata" tags={section.text_clues} />
              <TagList label="Container location tags" tags={section.iso6709} />
              <TagList label="Timestamps" tags={section.timestamps} />
              <TagList label="Device and orientation" tags={section.device} />
            </>
          )}
          <p className={MUTED}>
            Every value above is read as written in the file: it is easy to edit and is never proof
            of where the media was captured. Sources that disagree are both shown as found.
          </p>
          {section.ocr_available ? (
            <p className="text-sm">
              This analysis produced OCR text. Read it in the text panels for visible signs,
              addresses, and clocks —{" "}
              <a href={`#${sectionAnchor("ocr")}`} className="underline">
                Vestigo does not interpret that text
              </a>
              .
            </p>
          ) : (
            <p className={MUTED}>No OCR text was produced for this analysis.</p>
          )}
        </>
      )}

      <div className="space-y-3 border-t border-slate-200 pt-3 dark:border-slate-800">
        <h3 className="font-medium">Analyst location candidates</h3>
        {error ? (
          <div role="alert" className="space-y-2 text-sm">
            <p className="text-rose-800 dark:text-rose-300">
              The location candidates could not be loaded: {error}
            </p>
            <button type="button" onClick={() => void load()} className={BUTTON}>
              Retry
            </button>
          </div>
        ) : candidates === null ? (
          <p className={MUTED}>Loading…</p>
        ) : (
          <>
            <p className={MUTED}>{candidates.notice}</p>
            <CandidateForm artifactId={artifactId} section={section} onRecorded={changed} />
            {candidates.candidates.length === 0 ? (
              <p className={MUTED}>No location candidates recorded yet.</p>
            ) : (
              <ul aria-label="Location candidates" className="space-y-3">
                {candidates.candidates.map((candidate) => (
                  <CandidateRow
                    key={candidate.candidate_id}
                    artifactId={artifactId}
                    candidate={candidate}
                    mapEnabled={mapEnabled}
                    onChanged={changed}
                  />
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </Panel>
  );
}

function CandidateForm({
  artifactId,
  section,
  onRecorded,
}: {
  artifactId: string;
  section: LocationCluesSection | null;
  onRecorded: () => void;
}) {
  const [description, setDescription] = useState("");
  const [basis, setBasis] = useState("");
  const [assessment, setAssessment] = useState<AnalystAssessment | "">("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [notes, setNotes] = useState("");
  const [supports, setSupports] = useState<SupportRef[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Everything this artifact's current analysis can support a candidate with.
  const available: SupportRef[] = section
    ? [
        { type: "evidence_record", id: section.provenance.evidence_id },
        ...section.provenance.derived_files.map((file) => ({
          type: "derived_file" as SupportType,
          id: file.derived_file_id,
        })),
      ]
    : [];

  function toggleSupport(ref: SupportRef, checked: boolean) {
    setSupports((current) =>
      checked ? [...current, ref] : current.filter((item) => item.id !== ref.id),
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const pair = latitude !== "" && longitude !== "";
      await createLocationCandidate(artifactId, {
        description,
        basis,
        analyst_assessment: assessment as AnalystAssessment,
        ...(pair && { latitude: Number(latitude), longitude: Number(longitude) }),
        ...(notes && { notes }),
        ...(supports.length > 0 && { supports }),
      });
      setDescription("");
      setBasis("");
      setAssessment("");
      setLatitude("");
      setLongitude("");
      setNotes("");
      setSupports([]);
      onRecorded();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-2" aria-label="Record a location candidate">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-0.5">
          <span className={MUTED}>Place, as you would state it</span>
          <input className={INPUT} value={description} onChange={(e) => setDescription(e.target.value)} required />
        </label>
        <label className="space-y-0.5">
          <span className={MUTED}>Your assessment (your judgment, not a measurement)</span>
          <select
            className={INPUT}
            value={assessment}
            onChange={(e) => setAssessment(e.target.value as AnalystAssessment)}
            required
          >
            <option value="">Choose…</option>
            {ASSESSMENTS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-0.5">
          <span className={MUTED}>Latitude (optional)</span>
          <input className={INPUT} value={latitude} onChange={(e) => setLatitude(e.target.value)} inputMode="decimal" />
        </label>
        <label className="space-y-0.5">
          <span className={MUTED}>Longitude (optional, with latitude)</span>
          <input className={INPUT} value={longitude} onChange={(e) => setLongitude(e.target.value)} inputMode="decimal" />
        </label>
      </div>
      <label className="block space-y-0.5">
        <span className={MUTED}>Basis — why you think so (required)</span>
        <textarea className={INPUT} rows={2} value={basis} onChange={(e) => setBasis(e.target.value)} required />
      </label>
      <label className="block space-y-0.5">
        <span className={MUTED}>Notes</span>
        <textarea className={INPUT} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {available.length > 0 && (
        <fieldset className="space-y-1">
          <legend className={MUTED}>Supporting evidence held by Vestigo</legend>
          {available.map((ref) => (
            <label key={ref.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={supports.some((item) => item.id === ref.id)}
                onChange={(event) => toggleSupport(ref, event.target.checked)}
              />
              {SUPPORT_LABELS[ref.type]} <span className="font-mono text-xs">{ref.id.slice(0, 12)}…</span>
            </label>
          ))}
        </fieldset>
      )}
      {error && (
        <p role="alert" className="text-sm text-rose-800 dark:text-rose-300">
          {error}
        </p>
      )}
      <button type="submit" disabled={saving} className={`${BUTTON} disabled:opacity-40`}>
        Record candidate
      </button>
    </form>
  );
}

function CandidateRow({
  artifactId,
  candidate,
  mapEnabled,
  onChanged,
}: {
  artifactId: string;
  candidate: LocationCandidate;
  mapEnabled: boolean;
  onChanged: () => void;
}) {
  const [notes, setNotes] = useState(candidate.notes);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasCoordinates = candidate.latitude !== null && candidate.longitude !== null;

  async function patch(update: Parameters<typeof updateLocationCandidate>[2]) {
    setError(null);
    try {
      await updateLocationCandidate(artifactId, candidate.candidate_id, update);
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function remove() {
    setError(null);
    try {
      await deleteLocationCandidate(artifactId, candidate.candidate_id);
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <li className="space-y-1 rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <p className="flex flex-wrap items-baseline gap-2">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold dark:bg-slate-800">
          UNVERIFIED
        </span>
        <span className="font-medium">{candidate.description}</span>
      </p>
      <p className={MUTED}>
        Analyst assessment: {candidate.analyst_assessment} (the analyst's own judgment, not a
        measurement) · Recorded {formatDateTime(candidate.recorded_at)}
        {candidate.updated_at && ` · edited ${formatDateTime(candidate.updated_at)}`}
      </p>
      {hasCoordinates && (
        <p className="text-sm">
          <span className="font-mono">
            {candidate.latitude}, {candidate.longitude}
          </span>
          {mapEnabled && (
            <>
              {" · "}
              <a
                href={openStreetMapUrl(candidate.latitude!, candidate.longitude!)}
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                Open in OpenStreetMap (external)
              </a>
              <span className={`ml-2 ${MUTED}`}>{MAP_WARNING}</span>
            </>
          )}
        </p>
      )}
      <p className="text-sm">
        <span className="font-medium">Basis:</span> {candidate.basis}
      </p>
      {candidate.supports.length > 0 && (
        <p className={MUTED}>
          Supported by:{" "}
          {candidate.supports
            .map((ref) => `${SUPPORT_LABELS[ref.type]} ${ref.id.slice(0, 12)}…`)
            .join(", ")}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-xs">
          Assessment:
          <select
            className="rounded-md border border-slate-300 bg-white px-1 py-0.5 dark:border-slate-700 dark:bg-slate-900"
            value={candidate.analyst_assessment}
            onChange={(event) =>
              void patch({ analyst_assessment: event.target.value as AnalystAssessment })
            }
          >
            {ASSESSMENTS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-xs">
          Review:
          <select
            className="rounded-md border border-slate-300 bg-white px-1 py-0.5 dark:border-slate-700 dark:bg-slate-900"
            value={candidate.review_state}
            onChange={(event) => void patch({ review_state: event.target.value as ReviewState })}
          >
            {REVIEW_STATES.map((state) => (
              <option key={state} value={state}>
                {REVIEW_LABELS[state]}
              </option>
            ))}
          </select>
        </label>
        {confirming ? (
          <>
            <button
              type="button"
              onClick={() => void remove()}
              className={`${BUTTON} text-rose-800 dark:text-rose-300`}
            >
              Confirm delete
            </button>
            <button type="button" onClick={() => setConfirming(false)} className={BUTTON}>
              Keep
            </button>
          </>
        ) : (
          <button type="button" onClick={() => setConfirming(true)} className={BUTTON}>
            Delete candidate
          </button>
        )}
      </div>
      <label className="block space-y-0.5">
        <span className={MUTED}>Notes</span>
        <textarea className={INPUT} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {notes !== candidate.notes && (
        <button type="button" onClick={() => void patch({ notes })} className={BUTTON}>
          Save notes
        </button>
      )}
      {error && (
        <p role="alert" className="text-sm text-rose-800 dark:text-rose-300">
          {error}
        </p>
      )}
    </li>
  );
}
