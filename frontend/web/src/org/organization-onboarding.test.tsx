import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { ApiError, type RequestOptions } from "../api/client";
import type {
  CreatedOrganizationInvitation,
  Organization,
  OrganizationMembership,
} from "../api/types";
import {
  AuthContext,
  type AuthContextValue,
  type AuthorizedFetch,
} from "../auth/AuthContext";
import { OrganizationInvitations } from "../components/OrganizationInvitations";
import { OrganizationOnboarding } from "../components/OrganizationOnboarding";
import {
  OrganizationProvider,
} from "./OrganizationContext";
import { useOrganization } from "./useOrganization";

const ACCOUNT = {
  id: "account-1",
  email: "author@example.com",
  is_active: true,
  created_at: "2026-07-28T08:00:00Z",
};

const CREATED_ORGANIZATION: Organization = {
  id: "organization-created",
  name: "Northstar Research",
  role: "owner",
  created_at: "2026-07-28T09:00:00Z",
};

const JOINED_ORGANIZATION: Organization = {
  id: "organization-joined",
  name: "Joined Trials",
  role: "member",
  created_at: "2026-07-28T09:00:00Z",
};

interface FetchCall {
  path: string;
  options: RequestOptions | undefined;
}

function createFetcher(
  handler: (
    path: string,
    options: RequestOptions | undefined,
  ) => unknown | Promise<unknown>,
): { fetcher: AuthorizedFetch; calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  const fetcher: AuthorizedFetch = async <T,>(
    path: string,
    options?: RequestOptions,
  ): Promise<T> => {
    calls.push({ path, options });
    return (await handler(path, options)) as T;
  };
  return { fetcher, calls };
}

function OrganizationState() {
  const organization = useOrganization();
  return (
    <p>
      Organization state: {organization.status}; active:{" "}
      {organization.activeId ?? "none"}
    </p>
  );
}

function renderOnboarding(fetcher: AuthorizedFetch) {
  const auth: AuthContextValue = {
    status: "authenticated",
    account: ACCOUNT,
    signIn: async () => undefined,
    signOut: async () => undefined,
    authorizedFetch: fetcher,
  };
  return render(
    <AuthContext.Provider value={auth}>
      <OrganizationProvider>
        <OrganizationOnboarding />
        <OrganizationState />
      </OrganizationProvider>
    </AuthContext.Provider>,
  );
}

function membership(organizationId: string): OrganizationMembership {
  return {
    id: "membership-1",
    organization_id: organizationId,
    account_id: ACCOUNT.id,
    identity: {
      account_id: ACCOUNT.id,
      email: ACCOUNT.email,
      is_active: true,
    },
    role: "member",
    created_at: "2026-07-28T09:01:00Z",
  };
}

function invitation(
  organizationId: string,
): CreatedOrganizationInvitation {
  return {
    id: "invitation-1",
    organization_id: organizationId,
    email: "collaborator@example.com",
    role: "admin",
    invited_by_account_id: ACCOUNT.id,
    invited_by: {
      account_id: ACCOUNT.id,
      email: ACCOUNT.email,
      is_active: true,
    },
    expires_at: "2026-07-29T09:00:00Z",
    accepted_at: null,
    revoked_at: null,
    created_at: "2026-07-28T09:00:00Z",
    accept_url:
      "http://localhost:5173/invitations/accept?token=single-use-secret",
  };
}

describe("organization onboarding", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("creates and selects the first organization", async () => {
    const { fetcher, calls } = createFetcher((path, options) => {
      if (path === "/v1/organizations" && options === undefined) {
        return [];
      }
      if (
        path === "/v1/organizations" &&
        options?.method === "POST"
      ) {
        return CREATED_ORGANIZATION;
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const user = userEvent.setup();
    renderOnboarding(fetcher);

    expect(
      await screen.findByText(/Organization state: ready; active:\s+none/),
    ).toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Organization name"),
      "  Northstar Research  ",
    );
    await user.click(
      screen.getByRole("button", { name: "Create organization" }),
    );

    expect(
      await screen.findByText(
        "Northstar Research created. Opening your workspace…",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Organization state: ready; active:\s+organization-created/,
      ),
    ).toBeInTheDocument();
    expect(localStorage.getItem("trialscribe.activeOrganization")).toBe(
      CREATED_ORGANIZATION.id,
    );
    expect(calls).toContainEqual({
      path: "/v1/organizations",
      options: {
        method: "POST",
        json: { name: "Northstar Research" },
      },
    });
  });

  it("accepts a full invitation URL and selects the joined organization", async () => {
    let accepted = false;
    const { fetcher, calls } = createFetcher((path, options) => {
      if (path === "/v1/organization-invitations/accept") {
        accepted = true;
        return membership(JOINED_ORGANIZATION.id);
      }
      if (path === "/v1/organizations" && options === undefined) {
        return accepted ? [JOINED_ORGANIZATION] : [];
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const user = userEvent.setup();
    renderOnboarding(fetcher);

    await screen.findByText(/Organization state: ready; active:\s+none/);
    await user.click(
      screen.getByRole("tab", { name: "Join with invitation" }),
    );
    await user.type(
      screen.getByLabelText("Invitation link or token"),
      "https://app.example.com/invitations/accept?source=email&token=join-secret",
    );
    await user.click(
      screen.getByRole("button", { name: "Join organization" }),
    );

    expect(
      await screen.findByText(
        "You joined Joined Trials. Opening your workspace…",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Organization state: ready; active:\s+organization-joined/,
      ),
    ).toBeInTheDocument();
    expect(calls).toContainEqual({
      path: "/v1/organization-invitations/accept",
      options: {
        method: "POST",
        json: { token: "join-secret" },
      },
    });
  });

  it("shows a fixed create failure without leaking the server error", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (path === "/v1/organizations" && options === undefined) {
        return [];
      }
      throw new Error("private database topology");
    });
    const user = userEvent.setup();
    renderOnboarding(fetcher);

    await screen.findByText(/Organization state: ready; active:\s+none/);
    await user.type(
      screen.getByLabelText("Organization name"),
      "Northstar Research",
    );
    await user.click(
      screen.getByRole("button", { name: "Create organization" }),
    );

    expect(
      await screen.findByText(
        "Could not create the organization. Please try again.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("private database topology"),
    ).not.toBeInTheDocument();
  });

  it("switches tabs by keyboard and keeps each field contract", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (path === "/v1/organizations" && options === undefined) {
        return [];
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const user = userEvent.setup();
    renderOnboarding(fetcher);

    await screen.findByText(/Organization state: ready; active:\s+none/);
    const createTab = screen.getByRole("tab", {
      name: "Create organization",
    });
    const joinTab = screen.getByRole("tab", {
      name: "Join with invitation",
    });
    const name = screen.getByLabelText("Organization name");

    expect(createTab).toHaveAttribute("aria-selected", "true");
    expect(name).toHaveAttribute("maxlength", "120");
    expect(
      screen.queryByLabelText("Invitation link or token"),
    ).not.toBeInTheDocument();

    await user.type(name, "a".repeat(99));
    expect(screen.queryByText("99 / 120")).not.toBeInTheDocument();
    await user.type(name, "a");
    expect(screen.getByText("100 / 120")).toBeInTheDocument();

    createTab.focus();
    await user.keyboard("{ArrowRight}");
    expect(joinTab).toHaveFocus();
    expect(joinTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Invitation link or token")).toHaveAttribute(
      "autocomplete",
      "off",
    );

    await user.keyboard("{Home}");
    expect(createTab).toHaveFocus();
    expect(screen.getByLabelText("Organization name")).toHaveValue(
      "a".repeat(100),
    );
  });

  it("disables the create form while its request is pending", async () => {
    let resolveCreate: (organization: Organization) => void = () => undefined;
    const pendingCreate = new Promise<Organization>((resolve) => {
      resolveCreate = resolve;
    });
    const { fetcher } = createFetcher((path, options) => {
      if (path === "/v1/organizations" && options === undefined) {
        return [];
      }
      if (
        path === "/v1/organizations" &&
        options?.method === "POST"
      ) {
        return pendingCreate;
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const user = userEvent.setup();
    renderOnboarding(fetcher);

    await screen.findByText(/Organization state: ready; active:\s+none/);
    const name = screen.getByLabelText("Organization name");
    await user.type(name, "Northstar Research");
    await user.click(
      screen.getByRole("button", { name: "Create organization" }),
    );

    expect(screen.getByRole("button", { name: "Creating…" })).toBeDisabled();
    expect(name).toBeDisabled();

    await act(async () => {
      resolveCreate(CREATED_ORGANIZATION);
      await pendingCreate;
    });
    expect(
      await screen.findByText(
        "Northstar Research created. Opening your workspace…",
      ),
    ).toBeInTheDocument();
  });

  it("uses one safe message for invalid invitation responses", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (path === "/v1/organizations" && options === undefined) {
        return [];
      }
      if (path === "/v1/organization-invitations/accept") {
        throw new ApiError(422, "Invalid organization invitation");
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const user = userEvent.setup();
    renderOnboarding(fetcher);

    await screen.findByText(/Organization state: ready; active:\s+none/);
    await user.click(
      screen.getByRole("tab", { name: "Join with invitation" }),
    );
    await user.type(
      screen.getByLabelText("Invitation link or token"),
      "single-use-secret",
    );
    await user.click(
      screen.getByRole("button", { name: "Join organization" }),
    );

    expect(
      await screen.findByText(
        "This invitation is invalid or has expired. Ask the sender for a new link.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Invalid organization invitation"),
    ).not.toBeInTheDocument();
  });
});

describe("organization invitations", () => {
  it("lets owners generate admin invitations and reveals the link once", async () => {
    const organization = CREATED_ORGANIZATION;
    const createdInvitation = invitation(organization.id);
    const { fetcher, calls } = createFetcher(() => createdInvitation);
    const user = userEvent.setup();
    render(
      <OrganizationInvitations
        organization={organization}
        fetcher={fetcher}
      />,
    );

    await user.type(
      screen.getByLabelText("Collaborator email"),
      "collaborator@example.com",
    );
    await user.selectOptions(
      screen.getByLabelText("Organization role"),
      "admin",
    );
    await user.click(
      screen.getByRole("button", { name: "Create invitation" }),
    );

    const link = await screen.findByLabelText("Invitation link");
    expect(link).toHaveValue(createdInvitation.accept_url);
    expect(calls).toContainEqual({
      path: `/v1/organizations/${organization.id}/invitations`,
      options: {
        method: "POST",
        json: {
          email: "collaborator@example.com",
          role: "admin",
        },
      },
    });
  });

  it("limits admins to member invitations", async () => {
    const organization: Organization = {
      ...CREATED_ORGANIZATION,
      role: "admin",
    };
    const createdInvitation = {
      ...invitation(organization.id),
      role: "member" as const,
    };
    const { fetcher, calls } = createFetcher(() => createdInvitation);
    const user = userEvent.setup();
    render(
      <OrganizationInvitations
        organization={organization}
        fetcher={fetcher}
      />,
    );

    expect(
      screen.queryByRole("option", { name: "Admin" }),
    ).not.toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Collaborator email"),
      "member@example.com",
    );
    await user.click(
      screen.getByRole("button", { name: "Create invitation" }),
    );

    await waitFor(() => {
      expect(calls).toContainEqual({
        path: `/v1/organizations/${organization.id}/invitations`,
        options: {
          method: "POST",
          json: { email: "member@example.com", role: "member" },
        },
      });
    });
  });
});
