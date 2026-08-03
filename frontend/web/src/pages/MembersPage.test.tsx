import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Account, Organization, OrganizationMembership } from "../api/types";
import type { AuthContextValue, AuthorizedFetch } from "../auth/AuthContext";
import { AuthContext } from "../auth/AuthContext";
import type { OrganizationContextValue } from "../org/OrganizationContext";
import { OrganizationContext } from "../org/OrganizationContext";
import type { MembersReviewState } from "../product/accountAccessReviewFixtures";
import { MembersPage } from "./MembersPage";

const account: Account = {
  id: "account-live",
  email: "live@example.com",
  is_active: true,
  created_at: "2026-07-29T08:00:00Z",
};

const ownerOrganization: Organization = {
  id: "org-live",
  name: "Live Clinical Research",
  role: "owner",
  created_at: "2026-07-29T09:00:00Z",
};

function membership(organizationId: string, id = account.id): OrganizationMembership {
  return {
    id: `membership-${organizationId}-${id}`,
    organization_id: organizationId,
    account_id: id,
    role: id === account.id ? "owner" : "member",
    created_at: "2026-07-29T09:00:00Z",
  };
}

function contexts(
  organization: Organization,
  fetcher: AuthorizedFetch,
  organizations = [organization],
): { auth: AuthContextValue; organization: OrganizationContextValue } {
  return {
    auth: {
      status: "authenticated",
      account,
      signIn: async () => undefined,
      signOut: async () => undefined,
      authorizedFetch: fetcher,
    },
    organization: {
      status: "ready",
      organizations,
      activeId: organization.id,
      action: "idle",
      feedback: null,
      select: () => undefined,
      reload: () => undefined,
      create: async () => false,
      join: async () => false,
      dismissFeedback: () => undefined,
    },
  };
}

function page(
  values: ReturnType<typeof contexts>,
  review?: MembersReviewState,
) {
  return (
    <MemoryRouter>
      <AuthContext.Provider value={values.auth}>
        <OrganizationContext.Provider value={values.organization}>
          <MembersPage review={review} />
        </OrganizationContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

describe("MembersPage", () => {
  it("loads live members and invitation history for an owner", async () => {
    const fetcher = vi.fn(async (path: string) => {
      if (path.endsWith("/members")) {
        return [membership(ownerOrganization.id)];
      }
      if (path.endsWith("/invitations")) {
        return [];
      }
      throw new Error(`Unexpected request: ${path}`);
    }) as unknown as AuthorizedFetch;
    render(page(contexts(ownerOrganization, fetcher)));

    expect(
      await screen.findByRole("heading", { name: "Live Clinical Research" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("1 member")).toBeInTheDocument();
    expect(screen.getByText("No invitations have been created for this organization."))
      .toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith("/v1/organizations/org-live/members");
    expect(fetcher).toHaveBeenCalledWith(
      "/v1/organizations/org-live/invitations",
    );
  });

  it("does not request invitation administration for a member", async () => {
    const memberOrganization = { ...ownerOrganization, role: "member" as const };
    const fetcher = vi.fn(async (path: string) => {
      if (path.endsWith("/members")) {
        return [{ ...membership(memberOrganization.id), role: "member" }];
      }
      throw new Error(`Unexpected request: ${path}`);
    }) as unknown as AuthorizedFetch;
    render(page(contexts(memberOrganization, fetcher)));

    expect(await screen.findByText("Only organization owners and administrators can manage invitations."))
      .toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole("heading", { name: "Invitations" }),
    ).not.toBeInTheDocument();
  });

  it("ignores stale responses after the active organization changes", async () => {
    let resolveFirst: (value: OrganizationMembership[]) => void = () => undefined;
    const firstMembers = new Promise<OrganizationMembership[]>((resolve) => {
      resolveFirst = resolve;
    });
    const secondOrganization: Organization = {
      ...ownerOrganization,
      id: "org-second",
      name: "Second Organization",
    };
    const fetcher = vi.fn(async (path: string) => {
      if (path.includes("org-live/members")) {
        return firstMembers;
      }
      if (path.includes("org-second/members")) {
        return [membership("org-second", "second-account")];
      }
      if (path.endsWith("/invitations")) {
        return [];
      }
      throw new Error(`Unexpected request: ${path}`);
    }) as unknown as AuthorizedFetch;
    const first = contexts(ownerOrganization, fetcher, [
      ownerOrganization,
      secondOrganization,
    ]);
    const view = render(page(first));
    const second = contexts(secondOrganization, fetcher, [
      ownerOrganization,
      secondOrganization,
    ]);
    view.rerender(page(second));

    expect(await screen.findByText(/Member second-a/)).toBeInTheDocument();
    await act(async () => {
      resolveFirst([membership("org-live", "stale-account")]);
      await firstMembers;
    });
    expect(screen.queryByText(/stale-acc/)).not.toBeInTheDocument();
  });

  it("keeps review mutations local and renders success/error variants", async () => {
    const fetcher = vi.fn(async () => {
      throw new Error("Review must not request the API");
    }) as unknown as AuthorizedFetch;
    const values = contexts(ownerOrganization, fetcher);
    const user = userEvent.setup();
    const success = render(page(values, "success"));
    expect(screen.getByText("Invitation created")).toBeInTheDocument();
    success.unmount();

    const error = render(page(values, "error"));
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    error.unmount();

    render(page(values, "owner"));
    await user.click(screen.getAllByRole("button", { name: "Remove" })[0]);
    await user.click(screen.getByRole("button", { name: "Confirm remove" }));
    expect(await screen.findByText(/removed from this local review/i)).toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
