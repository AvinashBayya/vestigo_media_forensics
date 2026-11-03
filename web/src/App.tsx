import { Link, Route, Routes } from "react-router";

import { ArtifactPage } from "./pages/ArtifactPage";
import { LibraryPage } from "./pages/LibraryPage";
import { UploadPage } from "./pages/UploadPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LibraryPage />} />
      <Route path="/upload" element={<UploadPage />} />
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
        Back to the Library
      </Link>
    </div>
  );
}
