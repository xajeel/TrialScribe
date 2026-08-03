import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  changeOrganizationMemberRole,
  listOrganizationMembers,
  removeOrganizationMember,
} from "../api/organizations";
import {
  listOrganizationInvitations,
  revokeOrganizationInvitation,
} from "../api/invitations";
import type {
  OrganizationInvitation,
  OrganizationMembership,
  OrganizationRole,
} from "../api/types";
import { useAuth } from "../auth/useAuth";
import { AccountMenu } from "../components/AccountMenu";
import { AppLayout } from "../components/AppLayout";
import { OrganizationInvitations } from "../components/OrganizationInvitations";
import { OrganizationMembers } from "../components/OrganizationMembers";
import { useOrganization } from "../org/useOrganization";
import {
  membersFixtureFor,
  roleLabel,
  type MembersReviewState,
} from "../product/accountAccessReviewFixtures";

type LoadStatus = "loading" | "ready" | "error";

export function MembersPage({
  review,
}: {
  review?: MembersReviewState;
} = {}) {
  const { account, authorizedFetch } = useAuth();
  const organizationContext = useOrganization();
  const fixture = review === undefined ? null : membersFixtureFor(review);
  const activeOrganization =
    fixture?.organization ??
    organizationContext.organizations.find(
      (organization) => organization.id === organizationContext.activeId,
    ) ??
    null;
  const visibleAccount = fixture?.account ?? account;
  const [memberships, setMemberships] = useState<OrganizationMembership[]>(
    fixture === null ? [] : [...fixture.memberships],
  );
  const [invitations, setInvitations] = useState<OrganizationInvitation[]>(
    fixture === null ? [] : [...fixture.invitations],
  );
  const [membersStatus, setMembersStatus] = useState<LoadStatus>(
    fixture === null ? "loading" : "ready",
  );
  const [invitationsStatus, setInvitationsStatus] = useState<LoadStatus>(
    fixture === null ? "loading" : review === "error" ? "error" : "ready",
  );
  const [feedback, setFeedback] = useState<string | null>(null);
  const requestGeneration = useRef(0);

  const load = useCallback(async () => {
    if (review !== undefined || activeOrganization === null) {
      return;
    }
    const generation = ++requestGeneration.current;
    setMembersStatus("loading");
    setInvitationsStatus(
      activeOrganization.role === "member" ? "ready" : "loading",
    );
    setFeedback(null);

    const membersRequest = listOrganizationMembers(
      authorizedFetch,
      activeOrganization.id,
    );
    const invitationsRequest =
      activeOrganization.role === "member"
        ? Promise.resolve<OrganizationInvitation[]>([])
        : listOrganizationInvitations(authorizedFetch, activeOrganization.id);

    const [memberResult, invitationResult] = await Promise.allSettled([
      membersRequest,
      invitationsRequest,
    ]);
    if (generation !== requestGeneration.current) {
      return;
    }
    if (memberResult.status === "fulfilled") {
      setMemberships(memberResult.value);
      setMembersStatus("ready");
    } else {
      setMemberships([]);
      setMembersStatus("error");
    }
    if (invitationResult.status === "fulfilled") {
      setInvitations(invitationResult.value);
      setInvitationsStatus("ready");
    } else {
      setInvitations([]);
      setInvitationsStatus("error");
    }
  }, [activeOrganization, authorizedFetch, review]);

  useEffect(() => {
    void load();
    return () => {
      requestGeneration.current += 1;
    };
  }, [load]);

  if (visibleAccount === null) {
    return (
      <AppLayout>
        <div className="members-page members-page--loading" role="status">
          Loading account…
        </div>
      </AppLayout>
    );
  }

  if (activeOrganization === null) {
    return (
      <AppLayout actions={review === undefined ? <AccountMenu /> : undefined}>
        <div className="members-page members-page__no-organization">
          <p className="members-page__eyebrow">Organization settings</p>
          <h1>No active organization</h1>
          <p>Choose or create an organization before managing workspace access.</p>
          <Link to="/profile">Open profile settings</Link>
        </div>
      </AppLayout>
    );
  }

  const changeRole = async (
    membership: OrganizationMembership,
    role: OrganizationRole,
  ) => {
    setFeedback(null);
    if (review !== undefined) {
      setMemberships((current) =>
        current.map((item) =>
          item.id === membership.id ? { ...item, role } : item,
        ),
      );
      setFeedback(`Role updated to ${roleLabel(role)} for this review.`);
      return;
    }
    try {
      await changeOrganizationMemberRole(
        authorizedFetch,
        activeOrganization.id,
        membership.account_id,
        role,
      );
      await load();
      setFeedback("Member role updated.");
    } catch {
      setFeedback("Could not update the member role. Please try again.");
    }
  };

  const removeMember = async (membership: OrganizationMembership) => {
    setFeedback(null);
    if (review !== undefined) {
      setMemberships((current) =>
        current.filter((item) => item.id !== membership.id),
      );
      setFeedback("Member removed from this local review.");
      return;
    }
    try {
      await removeOrganizationMember(
        authorizedFetch,
        activeOrganization.id,
        membership.account_id,
      );
      await load();
      setFeedback("Member removed from the organization.");
    } catch {
      setFeedback("Could not remove the member. Please try again.");
    }
  };

  const revokeInvitation = async (invitation: OrganizationInvitation) => {
    setFeedback(null);
    if (review !== undefined) {
      setInvitations((current) =>
        current.map((item) =>
          item.id === invitation.id
            ? { ...item, revoked_at: "2026-08-03T15:00:00Z" }
            : item,
        ),
      );
      setFeedback("Invitation revoked in this local review.");
      return;
    }
    try {
      await revokeOrganizationInvitation(
        authorizedFetch,
        activeOrganization.id,
        invitation.id,
      );
      await load();
      setFeedback("Invitation revoked.");
    } catch {
      setFeedback("Could not revoke the invitation. Please try again.");
    }
  };

  const privileged =
    activeOrganization.role === "owner" || activeOrganization.role === "admin";

  return (
    <AppLayout actions={review === undefined ? <AccountMenu /> : undefined}>
      <div className="members-page">
        <header className="members-page__header">
          <div>
            <p className="members-page__eyebrow">Organization settings</p>
            <h1>{activeOrganization.name}</h1>
            <p>
              <span className="members-page__role">
                {roleLabel(activeOrganization.role)}
              </span>{" "}
              · Manage workspace access and create secure invitations.
            </p>
          </div>
          <div className="members-page__header-actions">
            {review === undefined && organizationContext.organizations.length > 1 && (
              <label>
                <span>Active organization</span>
                <select
                  value={activeOrganization.id}
                  onChange={(event) => organizationContext.select(event.target.value)}
                >
                  {organizationContext.organizations.map((organization) => (
                    <option key={organization.id} value={organization.id}>
                      {organization.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <Link to="/protocols">Back to protocols</Link>
          </div>
        </header>

        {fixture !== null && (
          <p className="members-page__review-note" role="note">
            {fixture.fixtureNote}
          </p>
        )}

        <OrganizationMembers
          account={visibleAccount}
          organization={activeOrganization}
          memberships={memberships}
          invitations={invitations}
          membersStatus={membersStatus}
          invitationsStatus={invitationsStatus}
          invitationPanel={
            privileged ? (
              <OrganizationInvitations
                key={activeOrganization.id}
                organization={activeOrganization}
                fetcher={review === undefined ? authorizedFetch : undefined}
                review={review !== undefined}
                initialResult={fixture?.createdInvitation}
                initialError={fixture?.invitationError}
                onCreated={(created) => {
                  if (review !== undefined) {
                    setInvitations((current) => [created, ...current]);
                  } else {
                    void load();
                  }
                }}
              />
            ) : undefined
          }
          review={review !== undefined}
          feedback={feedback}
          onRetry={() => void load()}
          onChangeRole={changeRole}
          onRemoveMember={removeMember}
          onRevokeInvitation={revokeInvitation}
        />
      </div>
    </AppLayout>
  );
}
