import { useState, type ReactNode } from "react";

import type {
  Account,
  Organization,
  OrganizationInvitation,
  OrganizationMembership,
  OrganizationRole,
} from "../api/types";
import {
  displayDate,
  invitationDisplayStatus,
  memberIdentity,
  roleLabel,
  shortIdentifier,
} from "../product/accountAccessReviewFixtures";

type LoadStatus = "loading" | "ready" | "error";

interface OrganizationMembersProps {
  account: Account;
  organization: Organization;
  memberships: ReadonlyArray<OrganizationMembership>;
  invitations: ReadonlyArray<OrganizationInvitation>;
  membersStatus: LoadStatus;
  invitationsStatus: LoadStatus;
  invitationPanel?: ReactNode;
  review?: boolean;
  feedback?: string | null;
  onRetry: () => void;
  onChangeRole: (
    membership: OrganizationMembership,
    role: OrganizationRole,
  ) => Promise<void>;
  onRemoveMember: (membership: OrganizationMembership) => Promise<void>;
  onRevokeInvitation: (
    invitation: OrganizationInvitation,
  ) => Promise<void>;
}

function roleCounts(memberships: ReadonlyArray<OrganizationMembership>) {
  return memberships.reduce(
    (counts, membership) => ({
      ...counts,
      [membership.role]: counts[membership.role] + 1,
    }),
    { owner: 0, admin: 0, member: 0 },
  );
}

export function OrganizationMembers({
  account,
  organization,
  memberships,
  invitations,
  membersStatus,
  invitationsStatus,
  invitationPanel,
  review = false,
  feedback,
  onRetry,
  onChangeRole,
  onRemoveMember,
  onRevokeInvitation,
}: OrganizationMembersProps) {
  const [roleDrafts, setRoleDrafts] = useState<Record<string, OrganizationRole>>(
    {},
  );
  const [confirmMemberId, setConfirmMemberId] = useState<string | null>(null);
  const [confirmInvitationId, setConfirmInvitationId] = useState<string | null>(
    null,
  );
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const privileged = organization.role === "owner" || organization.role === "admin";
  const counts = roleCounts(memberships);

  const changeRole = async (membership: OrganizationMembership) => {
    const nextRole = roleDrafts[membership.id] ?? membership.role;
    if (nextRole === membership.role) {
      return;
    }
    setPendingAction(`role-${membership.id}`);
    try {
      await onChangeRole(membership, nextRole);
    } finally {
      setPendingAction(null);
    }
  };

  const removeMember = async (membership: OrganizationMembership) => {
    setPendingAction(`remove-${membership.id}`);
    try {
      await onRemoveMember(membership);
      setConfirmMemberId(null);
    } finally {
      setPendingAction(null);
    }
  };

  const revokeInvitation = async (invitation: OrganizationInvitation) => {
    setPendingAction(`revoke-${invitation.id}`);
    try {
      await onRevokeInvitation(invitation);
      setConfirmInvitationId(null);
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <div className="organization-members">
      <nav className="organization-members__nav" aria-label="Organization settings">
        <a href="#organization-overview">Overview</a>
        <a href="#organization-members" aria-current="location">
          Members
        </a>
        {privileged && <a href="#organization-invitations">Invitations</a>}
      </nav>

      {!privileged && (
        <div className="organization-members__permission" role="note">
          Only organization owners and administrators can manage invitations.
        </div>
      )}

      {feedback !== null && feedback !== undefined && (
        <p className="organization-members__feedback" role="status">
          {feedback}
        </p>
      )}

      <section
        id="organization-overview"
        className="organization-members__summary"
        aria-label="Member summary"
      >
        <strong>
          {memberships.length} {memberships.length === 1 ? "member" : "members"}
        </strong>
        <span>
          {counts.owner} {counts.owner === 1 ? "owner" : "owners"} ·{" "}
          {counts.admin} {counts.admin === 1 ? "admin" : "admins"} ·{" "}
          {counts.member} {counts.member === 1 ? "member" : "members"}
        </span>
        <span>{organization.name}</span>
      </section>

      <section
        id="organization-members"
        className="organization-members__section"
        aria-labelledby="members-table-heading"
      >
        <div className="organization-members__section-heading">
          <div>
            <p className="organization-members__eyebrow">Workspace access</p>
            <h2 id="members-table-heading">Members</h2>
          </div>
          <span>{memberships.length} active</span>
        </div>

        {membersStatus === "loading" && (
          <div className="organization-members__loading" role="status">
            Loading organization members…
          </div>
        )}
        {membersStatus === "error" && (
          <div className="organization-members__error" role="alert">
            <p>Could not load organization members.</p>
            <button type="button" onClick={onRetry}>Try again</button>
          </div>
        )}
        {membersStatus === "ready" && memberships.length === 0 && (
          <p className="organization-members__empty">No memberships were returned.</p>
        )}
        {membersStatus === "ready" && memberships.length > 0 && (
          <div className="organization-members__table-wrap">
            <table className="organization-members__table">
              <thead>
                <tr>
                  <th scope="col">Member</th>
                  <th scope="col">Role</th>
                  <th scope="col">Joined</th>
                  <th scope="col">Status</th>
                  {privileged && <th scope="col">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {memberships.map((membership) => {
                  const identity = memberIdentity(membership, account);
                  const currentAccount = membership.account_id === account.id;
                  const canChangeRole =
                    organization.role === "owner" && !currentAccount;
                  const canRemove =
                    !currentAccount &&
                    (organization.role === "owner" ||
                      (organization.role === "admin" &&
                        membership.role === "member"));
                  const draft = roleDrafts[membership.id] ?? membership.role;
                  const rowBusy = pendingAction?.endsWith(membership.id) ?? false;
                  return (
                    <tr key={membership.id}>
                      <th scope="row" data-label="Member">
                        <span className="organization-members__avatar" aria-hidden="true">
                          {currentAccount ? "YO" : shortIdentifier(membership.account_id).slice(0, 2).toUpperCase()}
                        </span>
                        <span>
                          <strong>{identity.primary}</strong>
                          <small>{identity.secondary}</small>
                        </span>
                      </th>
                      <td data-label="Role">
                        {canChangeRole ? (
                          <select
                            aria-label={`Role for ${identity.primary}`}
                            value={draft}
                            disabled={rowBusy}
                            onChange={(event) =>
                              setRoleDrafts((current) => ({
                                ...current,
                                [membership.id]: event.target.value as OrganizationRole,
                              }))
                            }
                          >
                            <option value="member">Member</option>
                            <option value="admin">Admin</option>
                            <option value="owner">Owner</option>
                          </select>
                        ) : (
                          <span className={`organization-members__role organization-members__role--${membership.role}`}>
                            {roleLabel(membership.role)}
                          </span>
                        )}
                      </td>
                      <td data-label="Joined">{displayDate(membership.created_at)}</td>
                      <td data-label="Status">
                        <span className="organization-members__active">Active</span>
                      </td>
                      {privileged && (
                        <td data-label="Actions" className="organization-members__actions">
                          {canChangeRole && draft !== membership.role && (
                            <button
                              type="button"
                              disabled={rowBusy}
                              onClick={() => void changeRole(membership)}
                            >
                              {pendingAction === `role-${membership.id}`
                                ? "Updating…"
                                : "Update role"}
                            </button>
                          )}
                          {canRemove && confirmMemberId !== membership.id && (
                            <button
                              type="button"
                              className="organization-members__danger-action"
                              onClick={() => setConfirmMemberId(membership.id)}
                            >
                              Remove
                            </button>
                          )}
                          {confirmMemberId === membership.id && (
                            <div className="organization-members__confirm" role="group" aria-label={`Confirm removal of ${identity.primary}`}>
                              <span>Remove this member?</span>
                              <button
                                type="button"
                                disabled={rowBusy}
                                onClick={() => void removeMember(membership)}
                              >
                                {pendingAction === `remove-${membership.id}`
                                  ? "Removing…"
                                  : "Confirm remove"}
                              </button>
                              <button
                                type="button"
                                disabled={rowBusy}
                                onClick={() => setConfirmMemberId(null)}
                              >
                                Cancel
                              </button>
                            </div>
                          )}
                          {!canChangeRole && !canRemove && <span aria-label="No available actions">—</span>}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {privileged && (
        <section
          id="organization-invitations"
          className="organization-members__section organization-members__invitations"
          aria-labelledby="invitations-heading"
        >
          <div className="organization-members__section-heading">
            <div>
              <p className="organization-members__eyebrow">Single-use access</p>
              <h2 id="invitations-heading">Invitations</h2>
            </div>
          </div>
          <div className="organization-members__invite-layout">
            {invitationPanel}
            <div className="organization-members__history">
              <h3>Invitation history</h3>
              {invitationsStatus === "loading" && (
                <p role="status">Loading invitation history…</p>
              )}
              {invitationsStatus === "error" && (
                <div className="organization-members__error" role="alert">
                  <p>Could not load invitation history.</p>
                  <button type="button" onClick={onRetry}>Try again</button>
                </div>
              )}
              {invitationsStatus === "ready" && invitations.length === 0 && (
                <p className="organization-members__empty">
                  No invitations have been created for this organization.
                </p>
              )}
              {invitationsStatus === "ready" && invitations.length > 0 && (
                <div className="organization-members__table-wrap">
                  <table className="organization-members__table organization-members__table--invitations">
                    <thead>
                      <tr>
                        <th scope="col">Email</th>
                        <th scope="col">Role</th>
                        <th scope="col">Invited by</th>
                        <th scope="col">Created</th>
                        <th scope="col">Expires</th>
                        <th scope="col">Status</th>
                        <th scope="col">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invitations.map((invitation) => {
                        const status = invitationDisplayStatus(invitation);
                        const canRevoke =
                          status === "Pending" &&
                          (organization.role === "owner" ||
                            invitation.role === "member");
                        const busy = pendingAction === `revoke-${invitation.id}`;
                        return (
                          <tr key={invitation.id}>
                            <th scope="row" data-label="Email">{invitation.email}</th>
                            <td data-label="Role">{roleLabel(invitation.role)}</td>
                            <td data-label="Invited by">
                              {invitation.invited_by_account_id === account.id
                                ? "You"
                                : shortIdentifier(invitation.invited_by_account_id)}
                            </td>
                            <td data-label="Created">{displayDate(invitation.created_at)}</td>
                            <td data-label="Expires">{displayDate(invitation.expires_at)}</td>
                            <td data-label="Status">
                              <span className={`organization-members__invite-status organization-members__invite-status--${status.toLowerCase()}`}>
                                {status}
                              </span>
                            </td>
                            <td data-label="Action" className="organization-members__actions">
                              {canRevoke && confirmInvitationId !== invitation.id && (
                                <button
                                  type="button"
                                  className="organization-members__danger-action"
                                  onClick={() => setConfirmInvitationId(invitation.id)}
                                >
                                  Revoke
                                </button>
                              )}
                              {confirmInvitationId === invitation.id && (
                                <div className="organization-members__confirm" role="group" aria-label={`Confirm revocation for ${invitation.email}`}>
                                  <span>Revoke this invitation?</span>
                                  <button
                                    type="button"
                                    disabled={busy}
                                    onClick={() => void revokeInvitation(invitation)}
                                  >
                                    {busy ? "Revoking…" : "Confirm revoke"}
                                  </button>
                                  <button
                                    type="button"
                                    disabled={busy}
                                    onClick={() => setConfirmInvitationId(null)}
                                  >
                                    Cancel
                                  </button>
                                </div>
                              )}
                              {!canRevoke && <span aria-label="No available action">—</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="organization-members__history-note">
                Invitation links are never stored in this history.
              </p>
            </div>
          </div>
          {review && (
            <p className="organization-members__local-note">
              Review actions on this page are local and non-persistent.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
