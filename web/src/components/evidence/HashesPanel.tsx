import type { HashesSection } from "../../api/types";
import { Panel } from "../Panel";

export function HashesPanel({ section }: { section: HashesSection | null }) {
  return (
    <Panel title="File hashes" provenance={section?.provenance ?? null}>
      {section && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-2">
          <dt className="font-medium">SHA-256</dt>
          <dd className="font-mono text-xs break-all">{section.sha256}</dd>
          <dt className="font-medium">MD5</dt>
          <dd className="font-mono text-xs break-all">{section.md5}</dd>
          <dt className="font-medium">Integrity</dt>
          <dd>
            {section.matches_upload_record
              ? "The stored file matches the hashes recorded at upload."
              : "The stored file does not match the hashes recorded at upload."}
          </dd>
        </dl>
      )}
    </Panel>
  );
}
