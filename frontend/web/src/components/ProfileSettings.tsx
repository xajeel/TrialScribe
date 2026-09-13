import { useState } from "react";
import { Link } from "react-router-dom";

import type { Account, Organization } from "../api/types";
import type { OrganizationStatus } from "../org/OrganizationContext";
import { displayDate, roleLabel, shortIdentifier } from "../product/accountAccessReviewFixtures";
import { initialsOf } from "./AccountMenu";
import { OrganizationOnboarding } from "./OrganizationOnboarding";

interface ProfileSettingsProps {
  account: Account;
  organizations: ReadonlyArray<Organization>;
  activeId: string | null;
  organizationStatus: OrganizationStatus;
  onSelectOrganization: (id: string) => void;
  onRetryOrganizations: () => void;
  onSignOut: () => void;
  review?: boolean;
  fixtureNote?: string;
}

function DefinitionList({
  items,
}: {
  items: ReadonlyArray<{ term: string; description: string }>;
}) {
  return (
    <dl className="profile-settings__definitions">
      {items.map((item) => (
        <div key={item.term}>
          <dt>{item.term}</dt>
          <dd>{item.description}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ProfileSettings({
  account,
  organizations,
  activeId,
  organizationStatus,
  onSelectOrganization,
  onRetryOrganizations,
  onSignOut,
  review = false,
  fixtureNote,
}: ProfileSettingsProps) {
  const [copied, setCopied] = useState(false);
  const activeOrganization =
    organizations.find((organization) => organization.id === activeId) ?? null;

  const copyAccountId = async () => {
    try {
      await navigator.clipboard.writeText(account.id);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="profile-settings">
      <header className="profile-settings__page-header">
        <div>
          <p className="profile-settings__eyebrow">Account</p>
          <h1>Profile and settings</h1>
          <p>
            Manage your account, active organization, and current session.
          </p>
        </div>
        {account.is_active && (
          <Link className="profile-settings__back" to="/protocols">
            Back to protocols
          </Link>
        )}
      </header>

      {fixtureNote !== undefined && (
        <p className="profile-settings__review-note" role="note">
          {fixtureNote}
        </p>
      )}

      <div className="profile-settings__layout">
        <nav className="profile-settings__nav" aria-label="Profile settings">
          <a href="#profile-account" aria-current="location">
            Account
          </a>
          {account.is_active && (
            <>
              <a href="#profile-organizations">Organizations</a>
              <a href="#profile-access">Organization access</a>
            </>
          )}
          <a href="#profile-session">Session</a>
        </nav>

        <div className="profile-settings__content">
          <section
            id="profile-account"
            className="profile-settings__section"
            aria-labelledby="profile-account-heading"
          >
            <h2 id="profile-account-heading">Account</h2>
            <div className="profile-settings__identity">
              <span className="profile-settings__avatar" aria-hidden="true">
                {initialsOf(account.email)}
              </span>
              <div>
                <strong>{account.email}</strong>
                <p>
                  <span
                    className={`profile-settings__status profile-settings__status--${account.is_active ? "active" : "inactive"}`}
                  >
                    {account.is_active ? "Active" : "Inactive"}
                  </span>
                  <span>Member since {displayDate(account.created_at)}</span>
                </p>
              </div>
            </div>
            <DefinitionList
              items={[
                {
                  term: "Account ID",
                  description: shortIdentifier(account.id),
                },
                { term: "Email", description: account.email },
                {
                  term: "Status",
                  description: account.is_active ? "Active" : "Inactive",
                },
                {
                  term: "Created date",
                  description: displayDate(account.created_at),
                },
              ]}
            />
            <button
              type="button"
              className="profile-settings__copy"
              onClick={() => void copyAccountId()}
            >
              {copied ? "Copied" : "Copy account ID"}
            </button>
            <span className="sr-only" aria-live="polite">
              {copied ? "Account ID copied" : ""}
            </span>
            {!account.is_active && (
              <p className="profile-settings__inactive-note" role="status">
                This account is inactive. Protected organization and protocol
                content is unavailable. Log out and contact your administrator
                if you need access restored.
              </p>
            )}
          </section>

          {account.is_active && (
            <>
              <section
                id="profile-organizations"
                className="profile-settings__section"
                aria-labelledby="profile-organizations-heading"
              >
                <div className="profile-settings__section-heading">
                  <div>
                    <h2 id="profile-organizations-heading">Organizations</h2>
                    <p>
                      Your role controls which organization workspaces and
                      settings you can access.
                    </p>
                  </div>
                  {activeOrganization !== null && (
                    <Link to="/organization/members">
                      Organization access
                    </Link>
                  )}
                </div>

                {organizationStatus === "loading" && (
                  <div
                    className="profile-settings__skeletons"
                    aria-label="Loading your organizations"
                    role="status"
                  >
                    <span />
                    <span />
                  </div>
                )}
                {organizationStatus === "error" && (
                  <div className="profile-settings__inline-error" role="alert">
                    <p>Could not load your organizations.</p>
                    <button type="button" onClick={onRetryOrganizations}>
                      Try again
                    </button>
                  </div>
                )}
                {organizationStatus === "ready" && organizations.length === 0 && (
                  <p className="profile-settings__empty">
                    You are not a member of an organization.
                  </p>
                )}
                {organizationStatus === "ready" && organizations.length > 0 && (
                  <ul className="profile-settings__organizations">
                    {organizations.map((organization) => {
                      const active = organization.id === activeId;
                      return (
                        <li key={organization.id}>
                          <div>
                            <strong>{organization.name}</strong>
                            <p>
                              {roleLabel(organization.role)} · Created{" "}
                              {displayDate(organization.created_at)}
                            </p>
                          </div>
                          {active ? (
                            <span className="profile-settings__active-org">
                              Active workspace
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => onSelectOrganization(organization.id)}
                            >
                              Set active
                            </button>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
                <p className="profile-settings__helper">
                  The active organization applies across TrialScribe on this
                  browser.
                </p>
              </section>

              {organizationStatus === "ready" && (
                <section
                  id="profile-access"
                  className="profile-settings__section"
                  aria-labelledby="profile-access-heading"
                >
                  <h2 id="profile-access-heading">Organization access</h2>
                  <OrganizationOnboarding review={review} />
                </section>
              )}
            </>
          )}

          <section
            id="profile-session"
            className="profile-settings__section profile-settings__session"
            aria-labelledby="profile-session-heading"
          >
            <div>
              <h2 id="profile-session-heading">Session</h2>
              <p>You are signed in on this device.</p>
              <DefinitionList
                items={[{ term: "Session type", description: "Browser session" }]}
              />
            </div>
            <button type="button" onClick={onSignOut}>
              Log out
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}
