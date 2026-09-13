import type {
  Account,
  CreatedOrganizationInvitation,
  Organization,
  OrganizationInvitation,
  OrganizationMembership,
  OrganizationRole,
} from "../api/types";

/** Deterministic development-only presentation data for Screens 18 and 19. */
export type ProfileReviewState =
  | "populated"
  | "loading"
  | "error"
  | "inactive";

export type MembersReviewState =
  | "owner"
  | "admin"
  | "member"
  | "success"
  | "error";

export type InvitationDisplayStatus =
  | "Pending"
  | "Accepted"
  | "Expired"
  | "Revoked";

export interface ProfileReviewFixture {
  account: Account;
  organizations: ReadonlyArray<Organization>;
  activeId: string | null;
  organizationStatus: "ready" | "loading" | "error";
  fixtureNote: string;
}

export interface MembersReviewFixture {
  account: Account;
  organization: Organization;
  memberships: ReadonlyArray<OrganizationMembership>;
  invitations: ReadonlyArray<OrganizationInvitation>;
  createdInvitation?: CreatedOrganizationInvitation;
  invitationError?: string;
  fixtureNote: string;
}

const REVIEW_NOTE =
  "Development review — illustrative account and access data; actions are local and non-persistent.";

export const ACCOUNT_REVIEW: Account = {
  id: "acc-maya-6f3d-45a8-9142",
  email: "maya.chen@northstar-cr.org",
  is_active: true,
  created_at: "2026-07-15T14:22:01Z",
};

export const ORGANIZATION_REVIEW_OWNER: Organization = {
  id: "org-northstar-2026",
  name: "Northstar Clinical Research",
  role: "owner",
  created_at: "2026-07-15T14:24:00Z",
};

export const ORGANIZATION_REVIEW_MEMBER: Organization = {
  id: "org-arcadia-2026",
  name: "Arcadia Trials Group",
  role: "member",
  created_at: "2026-07-18T09:10:00Z",
};

const MEMBER_ROWS: ReadonlyArray<OrganizationMembership> = [
  {
    id: "membership-maya",
    organization_id: ORGANIZATION_REVIEW_OWNER.id,
    account_id: ACCOUNT_REVIEW.id,
    identity: {
      account_id: ACCOUNT_REVIEW.id,
      email: ACCOUNT_REVIEW.email,
      is_active: true,
    },
    role: "owner",
    created_at: "2026-07-15T14:24:00Z",
  },
  {
    id: "membership-omar",
    organization_id: ORGANIZATION_REVIEW_OWNER.id,
    account_id: "acc-omar-a20d-47d2-8064",
    identity: {
      account_id: "acc-omar-a20d-47d2-8064",
      email: "omar.shah@northstar-cr.org",
      is_active: true,
    },
    role: "admin",
    created_at: "2026-07-18T09:20:00Z",
  },
  {
    id: "membership-elena",
    organization_id: ORGANIZATION_REVIEW_OWNER.id,
    account_id: "acc-elena-b103-4c18-7231",
    identity: {
      account_id: "acc-elena-b103-4c18-7231",
      email: "elena.garcia@northstar-cr.org",
      is_active: false,
    },
    role: "member",
    created_at: "2026-07-21T12:05:00Z",
  },
];

const INVITATION_ROWS: ReadonlyArray<OrganizationInvitation> = [
  {
    id: "invite-pending",
    organization_id: ORGANIZATION_REVIEW_OWNER.id,
    email: "collaborator@example.com",
    role: "member",
    invited_by_account_id: ACCOUNT_REVIEW.id,
    invited_by: {
      account_id: ACCOUNT_REVIEW.id,
      email: ACCOUNT_REVIEW.email,
      is_active: true,
    },
    expires_at: "2026-08-05T12:00:00Z",
    accepted_at: null,
    revoked_at: null,
    created_at: "2026-08-01T12:00:00Z",
  },
  {
    id: "invite-accepted",
    organization_id: ORGANIZATION_REVIEW_OWNER.id,
    email: "accepted@example.com",
    role: "admin",
    invited_by_account_id: ACCOUNT_REVIEW.id,
    invited_by: {
      account_id: ACCOUNT_REVIEW.id,
      email: ACCOUNT_REVIEW.email,
      is_active: true,
    },
    expires_at: "2026-08-04T12:00:00Z",
    accepted_at: "2026-08-02T09:00:00Z",
    revoked_at: null,
    created_at: "2026-07-30T12:00:00Z",
  },
  {
    id: "invite-expired",
    organization_id: ORGANIZATION_REVIEW_OWNER.id,
    email: "expired@example.com",
    role: "member",
    invited_by_account_id: "acc-omar-a20d-47d2-8064",
    invited_by: {
      account_id: "acc-omar-a20d-47d2-8064",
      email: "omar.shah@northstar-cr.org",
      is_active: true,
    },
    expires_at: "2026-07-28T12:00:00Z",
    accepted_at: null,
    revoked_at: null,
    created_at: "2026-07-21T12:00:00Z",
  },
];

const CREATED_INVITATION: CreatedOrganizationInvitation = {
  ...INVITATION_ROWS[0],
  accept_url:
    "http://localhost:5173/invitations/accept?token=review-single-use-secret",
};

export function profileFixtureFor(
  state: ProfileReviewState,
): ProfileReviewFixture {
  return {
    account: {
      ...ACCOUNT_REVIEW,
      is_active: state !== "inactive",
    },
    organizations:
      state === "inactive"
        ? []
        : [ORGANIZATION_REVIEW_OWNER, ORGANIZATION_REVIEW_MEMBER],
    activeId: state === "inactive" ? null : ORGANIZATION_REVIEW_OWNER.id,
    organizationStatus:
      state === "loading" ? "loading" : state === "error" ? "error" : "ready",
    fixtureNote: REVIEW_NOTE,
  };
}

export function membersFixtureFor(
  state: MembersReviewState,
): MembersReviewFixture {
  const role: OrganizationRole =
    state === "admin" ? "admin" : state === "member" ? "member" : "owner";
  const organization = { ...ORGANIZATION_REVIEW_OWNER, role };
  return {
    account: ACCOUNT_REVIEW,
    organization,
    memberships: MEMBER_ROWS.map((item) =>
      item.account_id === ACCOUNT_REVIEW.id ? { ...item, role } : item,
    ),
    invitations:
      role === "member"
        ? []
        : role === "admin"
          ? INVITATION_ROWS.filter((invitation) => invitation.role === "member")
          : INVITATION_ROWS,
    createdInvitation: state === "success" ? CREATED_INVITATION : undefined,
    invitationError:
      state === "error"
        ? "An active invitation already exists for this email."
        : undefined,
    fixtureNote: REVIEW_NOTE,
  };
}

/** Short visual identifier that never implies an undisclosed person name. */
export function shortIdentifier(value: string): string {
  if (value.length <= 13) {
    return value;
  }
  return `${value.slice(0, 8)}…${value.slice(-4)}`;
}

export function roleLabel(role: OrganizationRole): string {
  return role[0].toUpperCase() + role.slice(1);
}

export function displayDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function invitationDisplayStatus(
  invitation: OrganizationInvitation,
  now = new Date(),
): InvitationDisplayStatus {
  if (invitation.accepted_at !== null) {
    return "Accepted";
  }
  if (invitation.revoked_at !== null) {
    return "Revoked";
  }
  if (new Date(invitation.expires_at).getTime() <= now.getTime()) {
    return "Expired";
  }
  return "Pending";
}

export function memberIdentity(
  membership: OrganizationMembership,
  account: Account,
): { primary: string; secondary: string } {
  return membership.account_id === account.id
    ? { primary: "You", secondary: membership.identity.email }
    : {
        primary: membership.identity.email,
        secondary: membership.identity.is_active
          ? "Active account"
          : "Inactive account",
      };
}
