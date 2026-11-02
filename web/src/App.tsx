import { Link, Route, Routes } from "react-router";

import { ArtifactPage } from "./pages/ArtifactPage";
import { UploadPage } from "./pages/UploadPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<UploadPage />} />
      <Route path="/artifacts/:artifactId" element={<ArtifactPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

function NotFound() {
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <Link to="/" className="text-sky-700 underline dark:text-sky-400">
        Back to uploads
      </Link>
    </div>
  );
}
