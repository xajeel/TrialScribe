import { useEffect, useState, type FormEvent } from "react";

import { createOrganizationInvitation } from "../api/invitations";
import type {
  InvitationRole,
  Organization,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";

const INVITE_ERROR =
  "Could not create the invitation. Check the email and try again.";

export function OrganizationInvitations({
  organization,
  fetcher,
}: {
  organization: Organization;
  fetcher: AuthorizedFetch;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InvitationRole>("member");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acceptUrl, setAcceptUrl] = useState<string | null>(null);

  useEffect(() => {
    setEmail("");
    setRole("member");
    setPending(false);
    setError(null);
    setAcceptUrl(null);
  }, [organization.id]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedEmail = email.trim();
    if (normalizedEmail === "" || pending) {
      return;
    }
    setPending(true);
    setError(null);
    setAcceptUrl(null);
    try {
      const created = await createOrganizationInvitation(
        fetcher,
        organization.id,
        normalizedEmail,
        role,
      );
      setAcceptUrl(created.accept_url);
      setEmail("");
    } catch {
      setError(INVITE_ERROR);
    } finally {
      setPending(false);
    }
  };

  return (
    <form className="organization-invite-form" onSubmit={submit}>
      <p className="card__text">
        Generate a single-use link for a collaborator. They must sign in with
        the invited email, then paste the link into Join organization.
      </p>
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
        />
      </div>
      <div className="field">
        <label className="field__label" htmlFor="invitation-role">
          Organization role
        </label>
        <select
          id="invitation-role"
          value={role}
          onChange={(event) =>
            setRole(event.target.value as InvitationRole)
          }
          disabled={pending}
        >
          <option value="member">Member</option>
          {organization.role === "owner" && (
            <option value="admin">Admin</option>
          )}
        </select>
      </div>
      <button
        type="submit"
        className="button button--primary"
        disabled={pending}
      >
        {pending ? "Creating invitation…" : "Create invitation"}
      </button>
      {error !== null && (
        <p className="organization-invite-form__error" role="alert">
          {error}
        </p>
      )}
      {acceptUrl !== null && (
        <div className="organization-invite-result" role="status">
          <label htmlFor="created-invitation-link">
            Invitation created — send this link securely
          </label>
          <textarea
            id="created-invitation-link"
            aria-label="Invitation link"
            value={acceptUrl}
            readOnly
            rows={3}
          />
        </div>
      )}
    </form>
  );
}
