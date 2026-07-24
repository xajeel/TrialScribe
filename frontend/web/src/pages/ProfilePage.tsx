import { AccountMenu, initialsOf } from "../components/AccountMenu";
import { AppLayout } from "../components/AppLayout";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/AsyncState";
import { useAuth } from "../auth/useAuth";
import { useOrganization } from "../org/useOrganization";

export function ProfilePage() {
  const { account, signOut } = useAuth();
  const org = useOrganization();

  const ready = org.status === "ready";
  const memberOfOrg = ready && org.organizations.length > 0;
  const email = account?.email ?? "";
  const memberSince =
    account === null
      ? ""
      : new Date(account.created_at).toLocaleDateString(undefined, {
          year: "numeric",
          month: "long",
          day: "numeric",
        });

  return (
    <AppLayout actions={<AccountMenu />}>
      <p className="eyebrow">Account</p>
      <h1 className="display">Profile and settings</h1>
      <p className="page-lead">
        Manage your account and workspace preferences.
      </p>

      <div className="workspace-grid">
        <section className="card" aria-labelledby="profile-card-title">
          <h2 className="card__title" id="profile-card-title">
            Profile
          </h2>
          <div className="profile-identity">
            <span className="avatar avatar--lg" aria-hidden="true">
              {initialsOf(email)}
            </span>
            <div>
              <p className="profile-identity__email">{email}</p>
              <span className="badge">
                {account?.is_active === false ? "Inactive" : "Active"}
              </span>
            </div>
          </div>
          <p className="card__text">Member since {memberSince}</p>
        </section>

        <section className="card" aria-labelledby="orgs-card-title">
          <h2 className="card__title" id="orgs-card-title">
            Organizations
          </h2>
          {org.status === "loading" && (
            <LoadingState label="Loading your organizations…" />
          )}
          {org.status === "error" && (
            <ErrorState
              message="Could not load your organizations."
              onRetry={org.reload}
            />
          )}
          {ready && org.organizations.length === 0 && (
            <EmptyState
              title="No organizations yet"
              description="You are not a member of any organization."
            />
          )}
          {memberOfOrg && (
            <ul className="org-list">
              {org.organizations.map((item) => (
                <li key={item.id} className="org-list__row">
                  <span className="org-list__name">{item.name}</span>
                  <span className="badge">{item.role}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card" aria-labelledby="prefs-card-title">
          <h2 className="card__title" id="prefs-card-title">
            Preferences
          </h2>
          {memberOfOrg ? (
            <div className="field">
              <label className="field__label" htmlFor="pref-organization">
                Active organization
              </label>
              <select
                id="pref-organization"
                value={org.activeId ?? ""}
                onChange={(event) => org.select(event.target.value)}
              >
                {org.organizations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              <span className="field__hint">
                Applies across your workspace on this device.
              </span>
            </div>
          ) : (
            <p className="card__text">
              Join an organization to set workspace preferences.
            </p>
          )}
        </section>

        <section className="card" aria-labelledby="session-card-title">
          <h2 className="card__title" id="session-card-title">
            Session
          </h2>
          <p className="card__text">You are signed in on this device.</p>
          <button
            type="button"
            className="button button--ghost card__action"
            onClick={() => void signOut()}
          >
            Log out
          </button>
        </section>
      </div>
    </AppLayout>
  );
}
