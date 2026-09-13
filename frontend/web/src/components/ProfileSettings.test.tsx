import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { OrganizationContextValue } from "../org/OrganizationContext";
import { OrganizationContext } from "../org/OrganizationContext";
import { profileFixtureFor } from "../product/accountAccessReviewFixtures";
import { ProfileSettings } from "./ProfileSettings";

const organizationContext: OrganizationContextValue = {
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

function renderProfile(
  state: "populated" | "loading" | "error" | "inactive" = "populated",
  overrides: Partial<React.ComponentProps<typeof ProfileSettings>> = {},
) {
  const fixture = profileFixtureFor(state);
  return render(
    <MemoryRouter>
      <OrganizationContext.Provider value={organizationContext}>
        <ProfileSettings
          account={fixture.account}
          organizations={fixture.organizations}
          activeId={fixture.activeId}
          organizationStatus={fixture.organizationStatus}
          onSelectOrganization={() => undefined}
          onRetryOrganizations={() => undefined}
          onSignOut={() => undefined}
          review
          fixtureNote={fixture.fixtureNote}
          {...overrides}
        />
      </OrganizationContext.Provider>
    </MemoryRouter>,
  );
}

describe("ProfileSettings", () => {
  it("renders immutable account facts and switches active organization", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    renderProfile("populated", { onSelectOrganization: onSelect });

    expect(
      screen.getByRole("heading", { name: "Profile and settings" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("maya.chen@northstar-cr.org"),
    ).toHaveLength(2);
    expect(screen.getByText("acc-maya…9142")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /edit profile/i }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Set active" }));
    expect(onSelect).toHaveBeenCalledWith("org-arcadia-2026");
    expect(
      screen
        .getAllByRole("link", { name: "Organization access" })
        .find((link) => link.getAttribute("href") === "/organization/members"),
    ).toBeDefined();
  });

  it("copies the full account ID with polite feedback", async () => {
    const writeText = vi.fn(async () => undefined);
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    renderProfile();

    await user.click(screen.getByRole("button", { name: "Copy account ID" }));
    expect(writeText).toHaveBeenCalledWith("acc-maya-6f3d-45a8-9142");
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(screen.getByText("Account ID copied")).toBeInTheDocument();
  });

  it("renders retryable loading and error organization states", async () => {
    const retry = vi.fn();
    const loading = renderProfile("loading");
    expect(
      screen.getByRole("status", { name: "Loading your organizations" }),
    ).toBeInTheDocument();
    loading.unmount();

    const user = userEvent.setup();
    renderProfile("error", { onRetryOrganizations: retry });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not load your organizations.",
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("limits inactive accounts to safe identity and session content", async () => {
    const onSignOut = vi.fn();
    const user = userEvent.setup();
    renderProfile("inactive", { onSignOut });

    expect(screen.getAllByText("Inactive").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/protected organization and protocol content is unavailable/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Organizations" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Back to protocols" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Log out" }));
    expect(onSignOut).toHaveBeenCalledOnce();
  });
});
