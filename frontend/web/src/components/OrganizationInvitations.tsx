import { useEffect, useRef, useState, type FormEvent } from "react";

import { createOrganizationInvitation } from "../api/invitations";
import { ApiError } from "../api/client";
import type {
  CreatedOrganizationInvitation,
  InvitationRole,
  Organization,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import { displayDate, roleLabel } from "../product/accountAccessReviewFixtures";

const INVITE_ERROR =
  "Could not create the invitation. Check the email and try again.";
const INVITE_CONFLICT =
  "This person is already a member or has an active invitation.";
const INVITE_PERMISSION =
  "You do not have permission to create this invitation.";

function safeInvitationError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    return INVITE_CONFLICT;
  }
  if (error instanceof ApiError && error.status === 403) {
    return INVITE_PERMISSION;
  }
  return INVITE_ERROR;
}

function reviewInvitation(
  organization: Organization,
  email: string,
  role: InvitationRole,
): CreatedOrganizationInvitation {
  return {
    id: "review-created-invitation",
    organization_id: organization.id,
    email,
    role,
    invited_by_account_id: "review-current-account",
    expires_at: "2026-08-10T12:00:00Z",
    accepted_at: null,
    revoked_at: null,
    created_at: "2026-08-03T12:00:00Z",
    accept_url:
      "http://localhost:5173/invitations/accept?token=review-single-use-secret",
  };
}

export function OrganizationInvitations({
  organization,
  fetcher,
  review = false,
  initialResult,
  initialError,
  onCreated,
}: {
  organization: Organization;
  fetcher?: AuthorizedFetch;
  review?: boolean;
  initialResult?: CreatedOrganizationInvitation;
  initialError?: string;
  onCreated?: (invitation: CreatedOrganizationInvitation) => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InvitationRole>("member");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(initialError ?? null);
  const [result, setResult] = useState<CreatedOrganizationInvitation | null>(
    initialResult ?? null,
  );
  const [copied, setCopied] = useState(false);
  const previousOrganizationId = useRef(organization.id);

  useEffect(() => {
    if (previousOrganizationId.current === organization.id) {
      return;
    }
    previousOrganizationId.current = organization.id;
    setEmail("");
    setRole("member");
    setPending(false);
    setError(null);
    setResult(null);
    setCopied(false);
  }, [organization.id]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedEmail = email.trim();
    if (normalizedEmail === "" || pending) {
      return;
    }
    setPending(true);
    setError(null);
    setResult(null);
    setCopied(false);
    try {
      const created = review
        ? reviewInvitation(organization, normalizedEmail, role)
        : await createOrganizationInvitation(
            fetcher as AuthorizedFetch,
            organization.id,
            normalizedEmail,
            role,
          );
      setResult(created);
      setEmail("");
      onCreated?.(created);
    } catch (caught) {
      setError(safeInvitationError(caught));
    } finally {
      setPending(false);
    }
  };

  const copyLink = async () => {
    if (result === null) {
      return;
    }
    try {
      await navigator.clipboard.writeText(result.accept_url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  if (result !== null) {
    return (
      <section className="organization-invite-result" aria-labelledby="invite-result-heading">
        <p className="organization-invite-result__status">Invitation created</p>
        <h3 id="invite-result-heading">
          Send this single-use link securely to {result.email}.
        </h3>
        <label htmlFor="created-invitation-link">Invitation link</label>
        <textarea
          id="created-invitation-link"
          aria-label="Invitation link"
          value={result.accept_url}
          readOnly
          rows={3}
        />
        <div className="organization-invite-result__actions">
          <button type="button" onClick={() => void copyLink()}>
            {copied ? "Copied" : "Copy link"}
          </button>
          <button
            type="button"
            onClick={() => {
              setResult(null);
              setCopied(false);
            }}
          >
            Create another
          </button>
        </div>
        <span className="sr-only" aria-live="polite">
          {copied ? "Invitation link copied" : ""}
        </span>
        <dl>
          <div>
            <dt>Role</dt>
            <dd>{roleLabel(result.role)}</dd>
          </div>
          <div>
            <dt>Expires</dt>
            <dd>{displayDate(result.expires_at)}</dd>
          </div>
          <div>
            <dt>Invited by</dt>
            <dd>You</dd>
          </div>
        </dl>
        <p className="organization-invite-result__notice">
          This link is shown only in this result. It is not available from
          invitation history.
        </p>
      </section>
    );
  }

  return (
    <form className="organization-invite-form" onSubmit={submit}>
      <div className="organization-invite-form__heading">
        <p className="organization-invite-form__eyebrow">Secure access</p>
        <h3>Invite a collaborator</h3>
        <p>
          Create a single-use invitation. The collaborator must sign in with
          the invited email.
        </p>
      </div>
      <div className="field">
        <label className="field__label" htmlFor="invitation-email">
          Collaborator email
        </label>
        <input
          id="invitation-email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="collaborator@example.com"
          required
          disabled={pending}
          aria-describedby={error === null ? undefined : "invitation-form-error"}
        />
      </div>
      <div className="field">
        <label className="field__label" htmlFor="invitation-role">
          Organization role
        </label>
        <select
          id="invitation-role"
          value={role}
          onChange={(event) => setRole(event.target.value as InvitationRole)}
          disabled={pending}
        >
          <option value="member">Member</option>
          {organization.role === "owner" && (
            <option value="admin">Admin</option>
          )}
        </select>
        <span className="field__hint">
          {role === "admin"
            ? "Admins can invite and remove members."
            : "Members can work in authorized protocols."}
        </span>
      </div>
      <button
        type="submit"
        className="button button--primary"
        disabled={pending}
      >
        {pending ? "Creating invitation…" : "Create invitation"}
      </button>
      {error !== null && (
        <p
          id="invitation-form-error"
          className="organization-invite-form__error"
          role="alert"
        >
          {error}
        </p>
      )}
    </form>
  );
}
