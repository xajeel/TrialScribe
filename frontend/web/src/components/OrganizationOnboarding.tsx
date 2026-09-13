import {
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { useOrganization } from "../org/useOrganization";

type SetupTab = "create" | "join";

export function OrganizationOnboarding({
  review = false,
}: {
  review?: boolean;
} = {}) {
  const organization = useOrganization();
  const [name, setName] = useState("");
  const [invitation, setInvitation] = useState("");
  const [activeTab, setActiveTab] = useState<SetupTab>("create");
  const createTabRef = useRef<HTMLButtonElement | null>(null);
  const joinTabRef = useRef<HTMLButtonElement | null>(null);

  const submitCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (review) {
      return;
    }
    if (await organization.create(name)) {
      setName("");
    }
  };

  const submitJoin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (review) {
      return;
    }
    if (await organization.join(invitation)) {
      setInvitation("");
    }
  };

  const busy = organization.action !== "idle";
  const showCharacterCount = name.length >= 100;

  const selectTab = (tab: SetupTab, moveFocus = false) => {
    setActiveTab(tab);
    if (moveFocus) {
      const target = tab === "create" ? createTabRef : joinTabRef;
      target.current?.focus();
    }
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    let nextTab: SetupTab | null = null;
    if (event.key === "ArrowLeft" || event.key === "Home") {
      nextTab = "create";
    }
    if (event.key === "ArrowRight" || event.key === "End") {
      nextTab = "join";
    }
    if (nextTab !== null) {
      event.preventDefault();
      selectTab(nextTab, true);
    }
  };

  return (
    <section
      className="organization-setup-panel"
      aria-label="Organization access"
    >
      <div
        className="organization-setup-tabs"
        role="tablist"
        aria-label="Organization setup options"
      >
        <button
          ref={createTabRef}
          id="organization-create-tab"
          type="button"
          role="tab"
          aria-selected={activeTab === "create"}
          aria-controls="organization-create-panel"
          tabIndex={activeTab === "create" ? 0 : -1}
          disabled={busy}
          onClick={() => selectTab("create")}
          onKeyDown={handleTabKeyDown}
        >
          Create organization
        </button>
        <button
          ref={joinTabRef}
          id="organization-join-tab"
          type="button"
          role="tab"
          aria-selected={activeTab === "join"}
          aria-controls="organization-join-panel"
          tabIndex={activeTab === "join" ? 0 : -1}
          disabled={busy}
          onClick={() => selectTab("join")}
          onKeyDown={handleTabKeyDown}
        >
          Join with invitation
        </button>
      </div>

      {organization.feedback !== null && (
        <div
          className={`organization-setup-feedback organization-setup-feedback--${organization.feedback.kind}`}
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

      {activeTab === "create" ? (
        <div
          id="organization-create-panel"
          className="organization-setup-panel__content"
          role="tabpanel"
          aria-labelledby="organization-create-tab"
        >
          <header className="organization-setup-panel__heading">
            <h2>Create an organization</h2>
            <p>
              Start a workspace you own. You can invite collaborators from
              organization settings.
            </p>
          </header>
          <form className="organization-setup-form" onSubmit={submitCreate}>
            <div className="organization-setup-field">
              <label htmlFor="organization-name">Organization name</label>
              <div className="organization-setup-field__control">
                <input
                  id="organization-name"
                  value={name}
                  maxLength={120}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Northstar Clinical Research"
                  required
                  disabled={busy}
                  aria-describedby="organization-name-note"
                />
                {showCharacterCount && (
                  <span
                    className="organization-setup-field__count"
                    aria-live="polite"
                  >
                    {name.length} / 120
                  </span>
                )}
              </div>
              <p id="organization-name-note">
                You will become the organization owner.
              </p>
            </div>
            <button
              type="submit"
              className="organization-setup-action"
              disabled={busy}
            >
              {organization.action === "creating"
                ? "Creating…"
                : "Create organization"}
            </button>
          </form>
        </div>
      ) : (
        <div
          id="organization-join-panel"
          className="organization-setup-panel__content"
          role="tabpanel"
          aria-labelledby="organization-join-tab"
        >
          <header className="organization-setup-panel__heading">
            <h2>Join an organization</h2>
            <p>
              Paste the full invitation link or token sent by an organization
              owner or administrator.
            </p>
          </header>
          <form className="organization-setup-form" onSubmit={submitJoin}>
            <div className="organization-setup-field">
              <label htmlFor="organization-invitation">
                Invitation link or token
              </label>
              <div className="organization-setup-field__control">
                <input
                  id="organization-invitation"
                  value={invitation}
                  onChange={(event) => setInvitation(event.target.value)}
                  placeholder="https://…?token=…"
                  autoComplete="off"
                  required
                  disabled={busy}
                  aria-describedby="organization-invitation-note"
                />
              </div>
              <p id="organization-invitation-note">
                The invitation determines your organization and role.
              </p>
            </div>
            <button
              type="submit"
              className="organization-setup-action organization-setup-action--secondary"
              disabled={busy}
            >
              {organization.action === "joining"
                ? "Joining…"
                : "Join organization"}
            </button>
          </form>
        </div>
      )}
    </section>
  );
}
