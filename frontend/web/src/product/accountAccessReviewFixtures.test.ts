import { describe, expect, it, vi } from "vitest";

import {
  changeOrganizationMemberRole,
  listOrganizationMembers,
  removeOrganizationMember,
} from "../api/organizations";
import {
  listOrganizationInvitations,
  revokeOrganizationInvitation,
} from "../api/invitations";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  ACCOUNT_REVIEW,
  invitationDisplayStatus,
  memberIdentity,
  membersFixtureFor,
  profileFixtureFor,
  shortIdentifier,
  type MembersReviewState,
  type ProfileReviewState,
} from "./accountAccessReviewFixtures";

describe("account and access review models", () => {
  it("provides every requested deterministic review state", () => {
    const profileStates: ProfileReviewState[] = [
      "populated",
      "loading",
      "error",
      "inactive",
    ];
    const memberStates: MembersReviewState[] = [
      "owner",
      "admin",
      "member",
      "success",
      "error",
    ];

    expect(profileStates.map(profileFixtureFor)).toHaveLength(4);
    expect(memberStates.map(membersFixtureFor)).toHaveLength(5);
    expect(membersFixtureFor("member").invitations).toEqual([]);
    expect(
      membersFixtureFor("admin").memberships.find(
        (membership) => membership.account_id === ACCOUNT_REVIEW.id,
      )?.role,
    ).toBe("admin");
    expect(membersFixtureFor("success").createdInvitation?.accept_url).toMatch(
      /single-use-secret/,
    );
    expect(profileFixtureFor("inactive").account.is_active).toBe(false);
  });

  it("formats privacy-safe member identities and invitation states", () => {
    const fixture = membersFixtureFor("owner");
    expect(memberIdentity(fixture.memberships[0], ACCOUNT_REVIEW)).toEqual({
      primary: "You",
      secondary: ACCOUNT_REVIEW.email,
    });
    expect(memberIdentity(fixture.memberships[1], ACCOUNT_REVIEW).primary).toMatch(
      /^Member acc-omar…8064$/,
    );
    expect(shortIdentifier("short-id")).toBe("short-id");
    expect(
      invitationDisplayStatus(
        fixture.invitations[0],
        new Date("2026-08-03T12:00:00Z"),
      ),
    ).toBe("Pending");
    expect(
      invitationDisplayStatus(
        fixture.invitations[1],
        new Date("2026-08-03T12:00:00Z"),
      ),
    ).toBe("Accepted");
    expect(
      invitationDisplayStatus(
        fixture.invitations[2],
        new Date("2026-08-03T12:00:00Z"),
      ),
    ).toBe("Expired");
  });

  it("maps every API helper to the implemented backend contract", async () => {
    const fetcher = vi.fn(async () => []) as unknown as AuthorizedFetch;

    await listOrganizationMembers(fetcher, "org-1");
    await changeOrganizationMemberRole(
      fetcher,
      "org-1",
      "account-2",
      "admin",
    );
    await removeOrganizationMember(fetcher, "org-1", "account-2");
    await listOrganizationInvitations(fetcher, "org-1");
    await revokeOrganizationInvitation(fetcher, "org-1", "invite-1");

    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "/v1/organizations/org-1/members",
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "/v1/organizations/org-1/members/account-2",
      { method: "PATCH", json: { role: "admin" } },
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      3,
      "/v1/organizations/org-1/members/account-2",
      { method: "DELETE" },
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      4,
      "/v1/organizations/org-1/invitations",
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      5,
      "/v1/organizations/org-1/invitations/invite-1",
      { method: "DELETE" },
    );
  });
});
