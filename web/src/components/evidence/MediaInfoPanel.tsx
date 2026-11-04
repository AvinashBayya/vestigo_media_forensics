import type { AudioStreamInfo, MediaInfoSection, VideoStreamInfo } from "../../api/types";
import { formatBytes, formatSeconds } from "../../lib/format";
import { Panel } from "../Panel";

const MUTED = "text-xs text-slate-600 dark:text-slate-400";

function dash(value: unknown, suffix = ""): string {
  return value === null || value === undefined ? "—" : `${value}${suffix}`;
}

export function MediaInfoPanel({ section }: { section: MediaInfoSection | null }) {
  return (
    <Panel title="Media information" provenance={section?.provenance ?? null}>
      {section && (
        <>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
            <dt className="font-medium">Container</dt>
            <dd>{section.container.format_long_name ?? section.container.format_name ?? "—"}</dd>
            <dt className="font-medium">Duration</dt>
            <dd>
              {formatSeconds(section.container.duration_seconds)}{" "}
              <span className={MUTED}>(container-reported, not decode-verified)</span>
            </dd>
            <dt className="font-medium">Size</dt>
            <dd>{section.container.size_bytes === null ? "—" : formatBytes(section.container.size_bytes)}</dd>
            <dt className="font-medium">Streams</dt>
            <dd>{section.container.stream_count}</dd>
          </dl>
          {section.video_streams.map((stream) => (
            <VideoStreamRow key={`v${stream.index}`} stream={stream} />
          ))}
          {section.audio_streams.map((stream) => (
            <AudioStreamRow key={`a${stream.index}`} stream={stream} />
          ))}
          {section.video_streams.length === 0 && <p className={MUTED}>No video stream.</p>}
          {section.audio_streams.length === 0 && <p className={MUTED}>No audio stream.</p>}
          <p className={MUTED}>
            Values are read from the container and stream headers as written. Audio is inspected from its
            headers only; nothing is decoded or transcribed.
          </p>
        </>
      )}
    </Panel>
  );
}

function VideoStreamRow({ stream }: { stream: VideoStreamInfo }) {
  return (
    <p className="text-sm">
      <span className="font-medium">Video:</span> {dash(stream.codec)}
      {stream.profile ? ` (${stream.profile})` : ""} · {dash(stream.width)}×{dash(stream.height)} ·{" "}
      {dash(stream.frame_rate, " fps")}
      {stream.rotation ? ` · display rotation ${stream.rotation}°` : ""}
      {stream.pixel_format ? ` · ${stream.pixel_format}` : ""}
    </p>
  );
}

function AudioStreamRow({ stream }: { stream: AudioStreamInfo }) {
  return (
    <p className="text-sm">
      <span className="font-medium">Audio:</span> {dash(stream.codec)} · {dash(stream.channels)}{" "}
      {stream.channels === 1 ? "channel" : "channels"}
      {stream.channel_layout ? ` (${stream.channel_layout})` : ""} · {dash(stream.sample_rate, " Hz")}
    </p>
  );
}
