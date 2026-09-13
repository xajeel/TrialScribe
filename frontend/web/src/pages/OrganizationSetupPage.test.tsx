import type { ReactNode } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { AuthContextValue } from "../auth/AuthContext";
import { AuthContext } from "../auth/AuthContext";
import type { OrganizationContextValue } from "../org/OrganizationContext";
import { OrganizationContext } from "../org/OrganizationContext";
import { renderApp } from "../test/renderApp";
import { DashboardPage } from "./DashboardPage";
import { OrganizationSetupPage } from "./OrganizationSetupPage";

const AUTH: AuthContextValue = {
  status: "authenticated",
  account: {
    id: "account-1",
    email: "author@example.com",
    is_active: true,
    created_at: "2026-07-29T08:00:00Z",
  },
  signIn: async () => undefined,
  signOut: async () => undefined,
  authorizedFetch: async <T,>(): Promise<T> => {
    throw new Error("Unexpected request");
  },
};

const EMPTY_ORGANIZATION: OrganizationContextValue = {
  status: "ready",
  organizations: [],
  activeId: null,
  action: "idle",
  feedback: null,
  select: () => undefined,
  reload: () => undefined,
  create: async () => false,
  join: async () => false,
  dismissFeedback: () => undefined,
};

function renderWithEmptyOrganization(element: ReactNode) {
  return render(
    <MemoryRouter>
      <AuthContext.Provider value={AUTH}>
        <OrganizationContext.Provider value={EMPTY_ORGANIZATION}>
          {element}
        </OrganizationContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("OrganizationSetupPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the complete organization setup hierarchy", async () => {
    const user = userEvent.setup();
    renderWithEmptyOrganization(<OrganizationSetupPage />);

    expect(
      screen.getByRole("heading", {
        name: "Where will your protocol work live?",
      }),
    ).toBeInTheDocument();
    const progress = screen.getByRole("navigation", {
      name: "Setup progress",
    });
    for (const step of ["Account", "Organization", "First protocol"]) {
      expect(within(progress).getByText(step)).toBeInTheDocument();
    }
    expect(
      screen.getByRole("button", { name: "Account menu" }),
    ).toHaveTextContent("AU");
    expect(
      screen.getByRole("link", { name: "TrialScribe protocols" }),
    ).toHaveAttribute("href", "/protocols");
    expect(
      screen.getByRole("link", { name: "TrialScribe protocols" }),
    ).toHaveClass("brand-logo");
    for (const role of ["Owner", "Admin", "Member"]) {
      expect(screen.getByText(role)).toBeInTheDocument();
    }
    for (const benefit of [
      "Isolated protocol data",
      "Role-based access",
      "Shared evidence and workspaces",
    ]) {
      expect(screen.getByRole("heading", { name: benefit })).toBeInTheDocument();
    }
    expect(screen.getByLabelText("Organization name")).toHaveAttribute(
      "maxlength",
      "120",
    );
    expect(screen.queryByLabelText(/research domain/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/notification/i)).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("tab", { name: "Join with invitation" }),
    );
    expect(
      screen.getByLabelText("Invitation link or token"),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Organization name")).not.toBeInTheDocument();
  });

  it("uses the dedicated page for a signed-in account without organizations", () => {
    renderWithEmptyOrganization(<DashboardPage />);

    expect(
      screen.getByRole("heading", {
        name: "Where will your protocol work live?",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("No organizations yet")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Signed in as author@example.com/),
    ).not.toBeInTheDocument();
  });

  it("opens the stable development review URL without login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (): Promise<Response> => {
        return new Response(
          JSON.stringify({ detail: "Invalid authentication credentials" }),
          {
            status: 401,
            headers: { "Content-Type": "application/json" },
          },
        );
      }),
    );

    renderApp({ route: "/review/organization-setup" });

    expect(
      await screen.findByRole("heading", {
        name: "Where will your protocol work live?",
      }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Review account MC")).toHaveTextContent("MC");
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  });
});
