import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { AuthContextValue } from "../auth/AuthContext";
import { AuthContext } from "../auth/AuthContext";
import type { OrganizationContextValue } from "../org/OrganizationContext";
import { OrganizationContext } from "../org/OrganizationContext";
import type { ProfileReviewState } from "../product/accountAccessReviewFixtures";
import { ProfilePage } from "./ProfilePage";

const account = {
  id: "account-live-2026",
  email: "author@example.com",
  is_active: true,
  created_at: "2026-07-29T08:00:00Z",
};

function renderProfilePage({
  review,
  signOut = vi.fn(async () => undefined),
  select = vi.fn(),
}: {
  review?: ProfileReviewState;
  signOut?: AuthContextValue["signOut"];
  select?: OrganizationContextValue["select"];
} = {}) {
  const auth: AuthContextValue = {
    status: "authenticated",
    account,
    signIn: async () => undefined,
    signOut,
    authorizedFetch: async <T,>(): Promise<T> => {
      throw new Error("Unexpected request");
    },
  };
  const organization: OrganizationContextValue = {
    status: "ready",
    organizations: [
      {
        id: "org-live-1",
        name: "Live Research",
        role: "owner",
        created_at: "2026-07-29T09:00:00Z",
      },
      {
        id: "org-live-2",
        name: "Second Research",
        role: "member",
        created_at: "2026-07-30T09:00:00Z",
      },
    ],
    activeId: "org-live-1",
    action: "idle",
    feedback: null,
    select,
    reload: () => undefined,
    create: async () => false,
    join: async () => false,
    dismissFeedback: () => undefined,
  };
  return {
    ...render(
      <MemoryRouter>
        <AuthContext.Provider value={auth}>
          <OrganizationContext.Provider value={organization}>
            <ProfilePage review={review} />
          </OrganizationContext.Provider>
        </AuthContext.Provider>
      </MemoryRouter>,
    ),
    select,
    signOut,
  };
}

describe("ProfilePage", () => {
  it("derives live account and organization behavior from providers", async () => {
    const user = userEvent.setup();
    const { select, signOut } = renderProfilePage();

    expect(screen.getAllByText("author@example.com").length).toBeGreaterThan(0);
    expect(screen.getByText("Live Research")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Set active" }));
    expect(select).toHaveBeenCalledWith("org-live-2");
    await user.click(screen.getByRole("button", { name: "Log out" }));
    expect(signOut).toHaveBeenCalledOnce();
  });

  it("keeps populated review organization switching local", async () => {
    const select = vi.fn();
    const user = userEvent.setup();
    renderProfilePage({ review: "populated", select });

    expect(screen.getByRole("note")).toHaveTextContent(/development review/i);
    await user.click(screen.getByRole("button", { name: "Set active" }));
    expect(select).not.toHaveBeenCalled();
    expect(screen.getByText("Active workspace")).toBeInTheDocument();
  });

  it("renders review loading, error, and inactive variants", () => {
    const loading = renderProfilePage({ review: "loading" });
    expect(
      screen.getByRole("status", { name: "Loading your organizations" }),
    ).toBeInTheDocument();
    loading.unmount();

    const error = renderProfilePage({ review: "error" });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not load your organizations.",
    );
    error.unmount();

    renderProfilePage({ review: "inactive" });
    expect(
      screen.queryByRole("heading", { name: "Organizations" }),
    ).not.toBeInTheDocument();
  });
});
