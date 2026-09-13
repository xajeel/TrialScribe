import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import type { AuthorizedFetch } from "../auth/AuthContext";
import { membersFixtureFor } from "../product/accountAccessReviewFixtures";
import { OrganizationInvitations } from "./OrganizationInvitations";
import { OrganizationMembers } from "./OrganizationMembers";

function renderMembers(
  state: "owner" | "admin" | "member" = "owner",
  callbacks: {
    onChangeRole?: React.ComponentProps<typeof OrganizationMembers>["onChangeRole"];
    onRemoveMember?: React.ComponentProps<typeof OrganizationMembers>["onRemoveMember"];
    onRevokeInvitation?: React.ComponentProps<typeof OrganizationMembers>["onRevokeInvitation"];
  } = {},
) {
  const fixture = membersFixtureFor(state);
  return render(
    <OrganizationMembers
      account={fixture.account}
      organization={fixture.organization}
      memberships={fixture.memberships}
      invitations={fixture.invitations}
      membersStatus="ready"
      invitationsStatus="ready"
      invitationPanel={
        state === "member" ? undefined : (
          <OrganizationInvitations organization={fixture.organization} review />
        )
      }
      review
      feedback={null}
      onRetry={() => undefined}
      onChangeRole={callbacks.onChangeRole ?? (async () => undefined)}
      onRemoveMember={callbacks.onRemoveMember ?? (async () => undefined)}
      onRevokeInvitation={
        callbacks.onRevokeInvitation ?? (async () => undefined)
      }
    />,
  );
}

describe("OrganizationMembers", () => {
  it("lets owners update roles and requires confirmation before removal", async () => {
    const onChangeRole = vi.fn(async () => undefined);
    const onRemoveMember = vi.fn(async () => undefined);
    const user = userEvent.setup();
    renderMembers("owner", { onChangeRole, onRemoveMember });

    expect(screen.getByText("3 members")).toBeInTheDocument();
    expect(
      screen.getAllByText("omar.shah@northstar-cr.org").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("elena.garcia@northstar-cr.org")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.queryByText(/acc-omar/)).not.toBeInTheDocument();
    const roleSelect = screen.getByRole("combobox", {
      name: /role for omar.shah@northstar-cr.org/i,
    });
    await user.selectOptions(roleSelect, "member");
    await user.click(screen.getAllByRole("button", { name: "Update role" })[0]);
    expect(onChangeRole).toHaveBeenCalledWith(
      expect.objectContaining({ account_id: "acc-omar-a20d-47d2-8064" }),
      "member",
    );

    await user.click(screen.getAllByRole("button", { name: "Remove" })[0]);
    expect(onRemoveMember).not.toHaveBeenCalled();
    const confirmation = screen.getByRole("group", {
      name: /confirm removal/i,
    });
    await user.click(
      within(confirmation).getByRole("button", { name: "Confirm remove" }),
    );
    expect(onRemoveMember).toHaveBeenCalledOnce();
  });

  it("requires confirmation before revoking a pending invitation", async () => {
    const onRevokeInvitation = vi.fn(async () => undefined);
    const user = userEvent.setup();
    renderMembers("owner", { onRevokeInvitation });

    await user.click(screen.getByRole("button", { name: "Revoke" }));
    expect(onRevokeInvitation).not.toHaveBeenCalled();
    const confirmation = screen.getByRole("group", {
      name: /confirm revocation/i,
    });
    await user.click(
      within(confirmation).getByRole("button", { name: "Confirm revoke" }),
    );
    expect(onRevokeInvitation).toHaveBeenCalledWith(
      expect.objectContaining({ email: "collaborator@example.com" }),
    );
    expect(screen.queryByRole("button", { name: "Copy link" })).not.toBeInTheDocument();
  });

  it("omits all administration controls for members", () => {
    renderMembers("member");

    expect(screen.getByRole("note")).toHaveTextContent(
      /only organization owners and administrators/i,
    );
    expect(
      screen.queryByRole("heading", { name: "Invitations" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("limits admin invitations and member actions to member scope", () => {
    renderMembers("admin");

    expect(screen.queryByRole("option", { name: "Admin" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(1);
    expect(screen.getByText("collaborator@example.com")).toBeInTheDocument();
    expect(screen.queryByText("accepted@example.com")).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Invited by" }))
      .toBeInTheDocument();
    expect(screen.getAllByText("You").length).toBeGreaterThan(0);
  });

  it("renders retryable load errors without private details", async () => {
    const fixture = membersFixtureFor("owner");
    const retry = vi.fn();
    const user = userEvent.setup();
    render(
      <OrganizationMembers
        account={fixture.account}
        organization={fixture.organization}
        memberships={[]}
        invitations={[]}
        membersStatus="error"
        invitationsStatus="error"
        onRetry={retry}
        onChangeRole={async () => undefined}
        onRemoveMember={async () => undefined}
        onRevokeInvitation={async () => undefined}
      />,
    );

    expect(screen.getAllByRole("alert")).toHaveLength(2);
    await user.click(screen.getAllByRole("button", { name: "Try again" })[0]);
    expect(retry).toHaveBeenCalledOnce();
  });
});

describe("OrganizationInvitations enhanced result", () => {
  it("shows a one-time result, copies it, and starts another", async () => {
    const fixture = membersFixtureFor("success");
    const user = userEvent.setup();
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(
      <OrganizationInvitations
        organization={fixture.organization}
        review
        initialResult={fixture.createdInvitation}
      />,
    );

    expect(screen.getByText("Invitation created")).toBeInTheDocument();
    const link = screen.getByLabelText("Invitation link");
    expect(link).toHaveValue(fixture.createdInvitation?.accept_url);
    await user.click(screen.getByRole("button", { name: "Copy link" }));
    expect(writeText).toHaveBeenCalledWith(fixture.createdInvitation?.accept_url);
    expect(screen.getByText("Invitation link copied")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create another" }));
    expect(
      screen.getByRole("button", { name: "Create invitation" }),
    ).toBeInTheDocument();
  });

  it("maps conflict and permission responses to safe messages", async () => {
    const fixture = membersFixtureFor("owner");
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(409, "private conflict"))
      .mockRejectedValueOnce(new ApiError(403, "private permission")) as unknown as AuthorizedFetch;
    const user = userEvent.setup();
    render(
      <OrganizationInvitations
        organization={fixture.organization}
        fetcher={fetcher}
      />,
    );

    const email = screen.getByLabelText("Collaborator email");
    await user.type(email, "member@example.com");
    await user.click(screen.getByRole("button", { name: "Create invitation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /already a member or has an active invitation/i,
    );
    await user.click(screen.getByRole("button", { name: "Create invitation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /do not have permission/i,
    );
    expect(screen.queryByText(/private/)).not.toBeInTheDocument();
  });
});
