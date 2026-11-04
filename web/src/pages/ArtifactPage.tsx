import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";

import {
  ApiError,
  contentUrl,
  deleteArtifact,
  errorMessage,
  getArtifact,
  getEvidence,
  getJob,
  getJobHistory,
  startAnalysis,
} from "../api/client";
import type { ArtifactDetail, EvidenceReport, JobHistoryItem, JobStatusResponse } from "../api/types";
import { AnalysisHistory } from "../components/AnalysisHistory";
import { DeleteArtifactDialog } from "../components/DeleteArtifactDialog";
import { DuplicateLibraryControl } from "../components/DuplicateLibraryControl";
import { ExportMenu } from "../components/ExportMenu";
import { C2PAPanel } from "../components/evidence/C2PAPanel";
import { DuplicatesPanel } from "../components/evidence/DuplicatesPanel";
import { KeyframeOCRPanel } from "../components/evidence/KeyframeOCRPanel";
import { KeyframePHashPanel } from "../components/evidence/KeyframePHashPanel";
import { KeyframesPanel } from "../components/evidence/KeyframesPanel";
import { MediaInfoPanel } from "../components/evidence/MediaInfoPanel";
import { SceneChangesPanel } from "../components/evidence/SceneChangesPanel";
import { HashesPanel } from "../components/evidence/HashesPanel";
import { MetadataPanel } from "../components/evidence/MetadataPanel";
import { OCRPanel } from "../components/evidence/OCRPanel";
import { PHashPanel } from "../components/evidence/PHashPanel";
import { JobProgress } from "../components/JobProgress";
import { ProblemsSummary } from "../components/ProblemsSummary";
import { EmptyState, ErrorState } from "../components/States";
import { ErrorBanner, EvidenceNotice, InfoBanner } from "../components/Messages";
import { ReviewPanel } from "../components/ReviewPanel";
import { ReviewProvider } from "../components/review/ReviewContext";
import { StatusBadge } from "../components/StatusBadge";
import { REVIEW_LABELS, formatBytes, formatDateTime, formatSeconds, isActive } from "../lib/format";

export const POLL_INTERVAL_MS = 1000;

export function ArtifactPage() {
  const { artifactId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const notice = (location.state as { notice?: string } | null)?.notice;

  const [artifact, setArtifact] = useState<ArtifactDetail | null>(null);
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [report, setReport] = useState<EvidenceReport | null>(null);
  const [history, setHistory] = useState<JobHistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [previewFailed, setPreviewFailed] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [detail, jobs] = await Promise.all([getArtifact(artifactId), getJobHistory(artifactId)]);
      setArtifact(detail);
      setHistory(jobs.jobs);
      const latest = detail.latest_job;
      if (latest && isActive(latest.status)) {
        setReport(null);
        setJob(await getJob(latest.job_id));
      } else {
        setJob(null);
        setReport(latest ? await getEvidence(artifactId, latest.job_id) : null);
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === "ARTIFACT_NOT_FOUND") setNotFound(true);
      else setLoadError(err instanceof ApiError ? err : new ApiError("UNKNOWN_ERROR", errorMessage(err), 0));
    }
  }, [artifactId]);

  async function viewJob(jobId: string) {
    setError(null);
    try {
      setReport(await getEvidence(artifactId, jobId));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!job || !isActive(job.status)) return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await getJob(job.job_id);
        if (isActive(next.status)) setJob(next);
        else await load();
      } catch (err) {
        setError(errorMessage(err));
      }
    }, POLL_INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [job, load]);

  async function runAnalysis() {
    setError(null);
    try {
      const created = await startAnalysis(artifactId, artifact?.media_type ?? "image");
      setReport(null);
      setJob(await getJob(created.job_id));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function confirmDelete() {
    if (!artifact) return;
    setDeleting(true);
    try {
      await deleteArtifact(artifactId);
      navigate("/", { state: { notice: `Deleted “${artifact.filename}” and all of its evidence.` } });
    } catch (err) {
      setError(errorMessage(err));
      setDeleting(false);
      setConfirmingDelete(false);
    }
  }

  if (notFound) {
    return <ErrorBanner message="This artifact does not exist. It may have been deleted." />;
  }
  if (!artifact) {
    if (loadError) return <ErrorState error={loadError} onRetry={() => void load()} title="This artifact could not be loaded." />;
    return error ? <ErrorBanner message={error} /> : <p role="status" className="text-sm text-slate-600">Loading…</p>;
  }

  const analysing = job !== null && isActive(job.status);
  const latestFinished = history.find((item) => !isActive(item.status)) ?? null;
  const shownJob = report ? (history.find((item) => item.job_id === report.job_id) ?? null) : null;
  const viewingEarlier = report !== null && latestFinished !== null && report.job_id !== latestFinished.job_id;

  return (
    <ReviewProvider artifactId={artifact.artifact_id}>
    <div className="space-y-5">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold break-all">{artifact.filename}</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {artifact.mime_type} · {formatBytes(artifact.size_bytes)}
          {artifact.width && artifact.height ? ` · ${artifact.width}×${artifact.height} px` : ""}
          {artifact.duration_seconds !== null ? ` · ${formatSeconds(artifact.duration_seconds)}` : ""} · uploaded{" "}
          {formatDateTime(artifact.created_at)} · review: {REVIEW_LABELS[artifact.review_state]}
        </p>
        <p className="font-mono text-xs text-slate-500">{artifact.artifact_id}</p>
      </header>

      <EvidenceNotice text={report?.notice} />
      {notice && <InfoBanner>{notice}</InfoBanner>}
      {error && <ErrorBanner message={error} />}
      {loadError && <ErrorState error={loadError} onRetry={() => void load()} title="This page could not be refreshed." />}

      <div className="grid gap-5 md:grid-cols-[18rem_1fr]">
        <aside className="space-y-4">
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
            {previewFailed ? (
              <p className="p-4 text-sm text-slate-600 dark:text-slate-400">
                {artifact.media_type === "video"
                  ? "This video cannot be played in the browser (codec or container not supported). The keyframes below show its content."
                  : "This format cannot be previewed in the browser."}
              </p>
            ) : artifact.media_type === "video" ? (
              // No transcoding (M3-6): the original streams with HTTP Range, or the fallback shows.
              <video
                src={contentUrl(artifact.artifact_id)}
                controls
                preload="metadata"
                aria-label={`Preview of ${artifact.filename}`}
                onError={() => setPreviewFailed(true)}
                className="max-h-80 w-full bg-black object-contain"
              />
            ) : (
              <img
                src={contentUrl(artifact.artifact_id)}
                alt={`Preview of ${artifact.filename}`}
                onError={() => setPreviewFailed(true)}
                className="max-h-80 w-full object-contain"
              />
            )}
          </div>

          <div className="flex flex-col gap-2 text-sm">
            <button
              type="button"
              onClick={runAnalysis}
              disabled={analysing}
              className="rounded-md border border-slate-300 px-3 py-1.5 font-medium disabled:opacity-40 dark:border-slate-700"
            >
              {artifact.latest_job ? "Run analysis again" : "Run analysis"}
            </button>
            <button
              type="button"
              onClick={() => setConfirmingDelete(true)}
              disabled={analysing}
              className="rounded-md border border-rose-300 px-3 py-1.5 font-medium text-rose-800 disabled:opacity-40 dark:border-rose-800 dark:text-rose-300"
            >
              Delete artifact
            </button>
          </div>

          {report && <ExportMenu artifactId={artifact.artifact_id} jobId={report.job_id} />}
          <ReviewPanel artifact={artifact} onSaved={setArtifact} />
          <AnalysisHistory jobs={history} viewingJobId={report?.job_id ?? null} onView={(jobId) => void viewJob(jobId)} />
          <DuplicateLibraryControl artifact={artifact} onChanged={setArtifact} />
        </aside>

        <div className="min-w-0 space-y-4">
          {job && <JobProgress job={job} />}
          {!job && !report && (
            <EmptyState
              title="This image has not been analysed yet"
              action={
                <button
                  type="button"
                  onClick={() => void runAnalysis()}
                  className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-slate-100 dark:text-slate-900"
                >
                  Run analysis
                </button>
              }
            >
              Analysis uses the default checks from Settings. Evidence appears here when it finishes.
            </EmptyState>
          )}
          {report && (
            <div key={report.job_id} className="space-y-4">
              {viewingEarlier && latestFinished && (
                <InfoBanner>
                  You are viewing an earlier analysis from {formatDateTime(report.job.created_at)}.{" "}
                  <button type="button" onClick={() => void viewJob(latestFinished.job_id)} className="font-medium underline">
                    View the latest analysis
                  </button>
                </InfoBanner>
              )}
              <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                <span>Analysis finished {formatDateTime(report.job.completed_at)}</span>
                <StatusBadge status={report.job.status} />
              </div>
              <ProblemsSummary report={report} job={shownJob} />
              <HashesPanel section={report.hashes} />
              {artifact.media_type === "video" ? (
                <>
                  <MediaInfoPanel section={report.media_info} />
                  <SceneChangesPanel section={report.scene_changes} />
                  <KeyframesPanel artifactId={artifact.artifact_id} section={report.keyframes} />
                  <DuplicatesPanel
                    section={report.duplicates}
                    addedSince={viewingEarlier ? null : artifact.added_since_analysis}
                    onRerun={analysing ? undefined : () => void runAnalysis()}
                  />
                  <KeyframeOCRPanel section={report.keyframe_ocr} />
                  <KeyframePHashPanel section={report.keyframe_phash} />
                </>
              ) : (
                <>
                  <C2PAPanel section={report.c2pa} />
                  <DuplicatesPanel
                    section={report.duplicates}
                    addedSince={viewingEarlier ? null : artifact.added_since_analysis}
                    onRerun={analysing ? undefined : () => void runAnalysis()}
                  />
                  <OCRPanel section={report.ocr} />
                  <PHashPanel section={report.perceptual_hash} />
                </>
              )}
              <MetadataPanel section={report.metadata} />
            </div>
          )}
        </div>
      </div>

      {confirmingDelete && (
        <DeleteArtifactDialog
          filename={artifact.filename}
          busy={deleting}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
    </ReviewProvider>
  );
}
