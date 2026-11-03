import { render } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router";

import { routes } from "../App";

export function renderApp(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return { ...render(<RouterProvider router={router} />), router };
}
