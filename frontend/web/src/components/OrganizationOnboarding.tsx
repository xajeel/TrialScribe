import { useState, type FormEvent } from "react";

import { useOrganization } from "../org/useOrganization";

export function OrganizationOnboarding() {
  const organization = useOrganization();
  const [name, setName] = useState("");
  const [invitation, setInvitation] = useState("");

  const submitCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (await organization.create(name)) {
      setName("");
    }
  };

  const submitJoin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (await organization.join(invitation)) {
      setInvitation("");
    }
  };

  const busy = organization.action !== "idle";

  return (
    <div className="organization-onboarding">
      {organization.feedback !== null && (
        <div
          className={`organization-feedback organization-feedback--${organization.feedback.kind}`}
          role={organization.feedback.kind === "error" ? "alert" : "status"}
        >
          <span>{organization.feedback.message}</span>
          <button
            type="button"
            onClick={organization.dismissFeedback}
            aria-label="Dismiss organization message"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="organization-onboarding__choices">
        <form className="organization-access-form" onSubmit={submitCreate}>
          <div>
            <h3>Create an organization</h3>
            <p>
              Start a workspace you own and invite collaborators when ready.
            </p>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="organization-name">
              Organization name
            </label>
            <input
              id="organization-name"
              value={name}
              maxLength={120}
              onChange={(event) => setName(event.target.value)}
              placeholder="Example Clinical Research"
              required
              disabled={busy}
            />
          </div>
          <button
            type="submit"
            className="button button--primary"
            disabled={busy}
          >
            {organization.action === "creating"
              ? "Creating…"
              : "Create organization"}
          </button>
        </form>

        <form className="organization-access-form" onSubmit={submitJoin}>
          <div>
            <h3>Join an organization</h3>
            <p>Paste the invitation link or token an organization sent you.</p>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="organization-invitation">
              Invitation link or token
            </label>
            <input
              id="organization-invitation"
              value={invitation}
              onChange={(event) => setInvitation(event.target.value)}
              placeholder="https://…?token=…"
              autoComplete="off"
              required
              disabled={busy}
            />
          </div>
          <button
            type="submit"
            className="button button--ghost"
            disabled={busy}
          >
            {organization.action === "joining"
              ? "Joining…"
              : "Join organization"}
          </button>
        </form>
      </div>
    </div>
  );
}
