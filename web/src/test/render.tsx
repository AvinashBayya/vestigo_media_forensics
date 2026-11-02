import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { AppRoutes } from "../App";
import { Layout } from "../components/Layout";

export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Layout>
        <AppRoutes />
      </Layout>
    </MemoryRouter>,
  );
}
