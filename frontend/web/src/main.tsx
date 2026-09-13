import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { OrganizationProvider } from "./org/OrganizationContext";

const rootElement = document.getElementById("root");

if (rootElement === null) {
  throw new Error("TrialScribe root element is missing");
}

createRoot(rootElement).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <OrganizationProvider>
          <App />
        </OrganizationProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
