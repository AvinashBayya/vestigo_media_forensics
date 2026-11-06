import { useEffect, useState, type ChangeEvent, type DragEvent, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { errorMessage, startAudioAnalysis, startImageAnalysis, startVideoAnalysis, uploadArtifact } from "../api/client";
import type { AnalysisOptions, AudioAnalysisOptions, VideoAnalysisOptions } from "../api/types";
import { formatBytes } from "../lib/format";
import { useSettings } from "../lib/settings";
import { ErrorBanner } from "./Messages";

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/tiff"];
const VIDEO_TYPES = [
  "video/mp4",
  "video/quicktime",
  "video/webm",
  "video/x-matroska",
  "video/x-msvideo",
  "video/mp2t",
  "video/x-ms-wmv",
  "video/x-flv",
  "video/3gpp",
  "video/x-m4v",
];

const IMAGE_EXTENSIONS = /\.(jpe?g|png|webp|tiff?)$/i;
const VIDEO_EXTENSIONS = /\.(mp4|mov|webm|mkv|avi|ts|wmv|flv|3gp|m4v)$/i;
const MAX_IMAGE_BYTES = 50 * 1024 * 1024;
const MAX_VIDEO_BYTES = 500 * 1024 * 1024;

const AUDIO_TYPES = ["audio/wav", "audio/x-wav", "audio/mpeg", "audio/flac", "audio/ogg", "audio/mp4", "audio/x-m4a"];
const AUDIO_EXTENSIONS = /\.(wav|mp3|flac|ogg|m4a)$/i;
const ACCEPTED_TYPES = [...IMAGE_TYPES, ...VIDEO_TYPES, ...AUDIO_TYPES];
const MAX_AUDIO_BYTES = 200 * 1024 * 1024;

type MediaKind = "image" | "video" | "audio";

function kindOf(file: File): MediaKind | null {
  if (IMAGE_TYPES.includes(file.type) || IMAGE_EXTENSIONS.test(file.name)) return "image";
  if (VIDEO_TYPES.includes(file.type) || VIDEO_EXTENSIONS.test(file.name)) return "video";
  if (AUDIO_TYPES.includes(file.type) || AUDIO_EXTENSIONS.test(file.name)) return "audio";
  return null;
}

export const OPTION_LABELS: Record<keyof AnalysisOptions, string> = {
  metadata: "Embedded metadata (EXIF, XMP, IPTC)",
  c2pa: "Content Credentials (C2PA) validation",
  ocr: "Text in image (OCR, English)",
  duplicate_search: "Duplicate search in the local library",
};

export const AUDIO_OPTION_LABELS: Record<keyof AudioAnalysisOptions, string> = {
  metadata: "Embedded metadata (ID3 and container tags)",
  c2pa: "Content Credentials (C2PA) validation",
  duplicate_search: "Duplicate search (byte-identical files only)",
};

export const VIDEO_OPTION_LABELS: Record<keyof VideoAnalysisOptions, string> = {
  metadata: "Embedded metadata (QuickTime, Matroska, XMP)",
  c2pa: "Content Credentials (C2PA) validation",
  scene_detection: "Scene-change detection",
  keyframe_ocr: "Text in keyframes (OCR, English, up to 10 frames)",
  duplicate_search: "Duplicate search in the local library",
};

type Phase = "idle" | "uploading" | "starting";

export function UploadForm() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const { settings, loaded: settingsLoaded } = useSettings();
  const autoAnalyze = settings.auto_analyze_after_upload;
  const [options, setOptions] = useState<AnalysisOptions>(settings.default_analysis_options);
  const [videoOptions, setVideoOptions] = useState<VideoAnalysisOptions>(settings.default_video_analysis_options);
  const [audioOptions, setAudioOptions] = useState<AudioAnalysisOptions>(settings.default_audio_analysis_options);
  const [optionsTouched, setOptionsTouched] = useState(false);

  // Start from the saved defaults once they arrive, unless the analyst already changed the options.
  useEffect(() => {
    if (settingsLoaded && !optionsTouched) {
      setOptions(settings.default_analysis_options);
      setVideoOptions(settings.default_video_analysis_options);
      setAudioOptions(settings.default_audio_analysis_options);
    }
  }, [settingsLoaded, optionsTouched, settings.default_analysis_options, settings.default_video_analysis_options]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function selectFile(selected: File | undefined) {
    setError(null);
    if (!selected) return;
    const kind = kindOf(selected);
    if (kind === null) {
      setFile(null);
      setError(
        "Only JPEG, PNG, WebP, and TIFF images, MP4, MOV, WebM, MKV, AVI, MPEG-TS, WMV, FLV, and 3GP videos, and WAV, MP3, FLAC, OGG, and M4A audio files are supported.",
      );
      return;
    }
    const limit = kind === "video" ? MAX_VIDEO_BYTES : kind === "audio" ? MAX_AUDIO_BYTES : MAX_IMAGE_BYTES;
    const limitLabel = kind === "video" ? "500" : kind === "audio" ? "200" : "50";
    if (selected.size > limit) {
      setFile(null);
      setError(`The file is larger than the ${limitLabel} MB limit for ${kind} files.`);
      return;
    }
    setFile(selected);
  }

  const fileKind: MediaKind = file ? (kindOf(file) ?? "image") : "image";

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files[0]);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setError(null);
    setPhase("uploading");
    setProgress(0);
    let artifactId: string;
    try {
      artifactId = (await uploadArtifact(file, setProgress)).artifact_id;
    } catch (err) {
      setError(errorMessage(err));
      setPhase("idle");
      return;
    }
    if (!autoAnalyze) {
      navigate(`/artifacts/${artifactId}`, {
        state: { notice: "Uploaded. Analysis was not started because automatic analysis is off in Settings." },
      });
      return;
    }
    setPhase("starting");
    try {
      if (fileKind === "video") await startVideoAnalysis(artifactId, videoOptions);
      else if (fileKind === "audio") await startAudioAnalysis(artifactId, audioOptions);
      else await startImageAnalysis(artifactId, options);
      navigate(`/artifacts/${artifactId}`);
    } catch (err) {
      // The upload worked; the artifact page lets the analyst retry the analysis.
      navigate(`/artifacts/${artifactId}`, {
        state: { notice: `The file was uploaded, but analysis could not start: ${errorMessage(err)}` },
      });
    }
  }

  const busy = phase !== "idle";

  return (
    <form onSubmit={onSubmit} className="space-y-4" aria-busy={busy}>
      <label
        htmlFor="file-input"
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed px-4 py-10 text-center has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-sky-600 ${
          dragging
            ? "border-sky-500 bg-sky-50 dark:bg-sky-950"
            : "border-slate-300 bg-white hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900"
        }`}
      >
        <span className="font-medium">{file ? file.name : "Choose an image or drop it here"}</span>
        <span className="text-xs text-slate-600 dark:text-slate-400">
          {file
            ? formatBytes(file.size)
            : "Images up to 50 MB · videos (MP4, MOV, WebM, MKV, AVI, TS, WMV, FLV, 3GP) up to 500 MB · audio (WAV, MP3, FLAC, OGG, M4A) up to 200 MB"}
        </span>
        <input
          id="file-input"
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          className="sr-only"
          disabled={busy}
          onChange={(event: ChangeEvent<HTMLInputElement>) => selectFile(event.target.files?.[0])}
        />
      </label>

      {!autoAnalyze && (
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Automatic analysis after upload is off (Settings). You can start the analysis from the artifact page.
        </p>
      )}
      <fieldset className="space-y-1" disabled={busy} hidden={!autoAnalyze}>
        <legend className="mb-1 text-sm font-medium">Checks to run</legend>
        {fileKind === "audio" &&
          (Object.keys(AUDIO_OPTION_LABELS) as (keyof AudioAnalysisOptions)[]).map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={audioOptions[key]}
                onChange={(event) => {
                  setOptionsTouched(true);
                  setAudioOptions({ ...audioOptions, [key]: event.target.checked });
                }}
              />
              {AUDIO_OPTION_LABELS[key]}
            </label>
          ))}
        {fileKind === "video"
          ? (Object.keys(VIDEO_OPTION_LABELS) as (keyof VideoAnalysisOptions)[]).map((key) => (
              <label key={key} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={videoOptions[key]}
                  onChange={(event) => {
                    setOptionsTouched(true);
                    setVideoOptions({ ...videoOptions, [key]: event.target.checked });
                  }}
                />
                {VIDEO_OPTION_LABELS[key]}
              </label>
            ))
          : fileKind === "audio"
            ? null
            : (Object.keys(OPTION_LABELS) as (keyof AnalysisOptions)[]).map((key) => (
              <label key={key} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={options[key]}
                  onChange={(event) => {
                    setOptionsTouched(true);
                    setOptions({ ...options, [key]: event.target.checked });
                  }}
                />
                {OPTION_LABELS[key]}
              </label>
            ))}
        <p className="text-xs text-slate-600 dark:text-slate-400">
          {fileKind === "video"
            ? "File hashes, media information, keyframes, and keyframe perceptual hashes always run."
            : fileKind === "audio"
              ? "File hashes and media information always run. No audio is decoded or transcribed."
              : "File hashes and the perceptual hash always run."}
        </p>
      </fieldset>

      {error && <ErrorBanner message={error} />}

      {busy && (
        <div className="space-y-1" aria-live="polite">
          <div
            role="progressbar"
            aria-label="Upload progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress}
            className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800"
          >
            <div className="h-full bg-sky-600 transition-all" style={{ width: `${progress}%` }} />
          </div>
          <p className="text-sm">{phase === "uploading" ? `Uploading… ${progress}%` : "Starting analysis…"}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={!file || busy}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900"
      >
        {autoAnalyze ? "Upload and analyse" : "Upload"}
      </button>
    </form>
  );
}
