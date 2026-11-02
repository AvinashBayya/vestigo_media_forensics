import { useLocation } from "react-router";

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
        <h2 className="font-medium">Recent uploads</h2>
        <RecentArtifacts />
      </section>
    </div>
  );
}
