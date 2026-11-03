import { Link, useLocation } from "react-router";

import { EvidenceNotice, InfoBanner } from "../components/Messages";
import { RecentArtifacts } from "../components/RecentArtifacts";
import { UploadForm } from "../components/UploadForm";

export function UploadPage() {
  const location = useLocation();
  const notice = (location.state as { notice?: string } | null)?.notice;

  return (
    <div className="space-y-8">
      <section className="max-w-2xl space-y-4">
        <h1 className="text-xl font-semibold">Analyse an image</h1>
        <EvidenceNotice />
        {notice && <InfoBanner>{notice}</InfoBanner>}
        <UploadForm />
      </section>
      <section className="space-y-2">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-medium">Recent uploads</h2>
          <Link to="/" className="text-sm text-sky-700 underline dark:text-sky-400">
            View the Library
          </Link>
        </div>
        <RecentArtifacts />
      </section>
    </div>
  );
}
