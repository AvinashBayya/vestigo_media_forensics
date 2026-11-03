import { Link, Outlet, type RouteObject } from "react-router";

import { Layout } from "./components/Layout";
import { ArtifactPage } from "./pages/ArtifactPage";
import { LibraryPage } from "./pages/LibraryPage";
import { UploadPage } from "./pages/UploadPage";

/** Route objects for a data router, which `useBlocker` (unsaved-changes guard) requires. */
export const routes: RouteObject[] = [
  {
    element: (
      <Layout>
        <Outlet />
      </Layout>
    ),
    children: [
      { index: true, element: <LibraryPage /> },
      { path: "upload", element: <UploadPage /> },
      { path: "artifacts/:artifactId", element: <ArtifactPage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];

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
