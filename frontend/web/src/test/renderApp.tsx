import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import App from "../App";
import { AuthProvider } from "../auth/AuthContext";
import { OrganizationProvider } from "../org/OrganizationContext";

/** Render the full app under a memory router at `route`, with all providers. */
export function renderApp({ route = "/" }: { route?: string } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <OrganizationProvider>
          <App />
        </OrganizationProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}
