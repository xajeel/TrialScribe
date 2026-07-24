import { AccountMenu } from "../components/AccountMenu";
import { AppLayout } from "../components/AppLayout";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/AsyncState";
import { useAuth } from "../auth/useAuth";
import { useOrganization } from "../org/useOrganization";

export function DashboardPage() {
  const { account } = useAuth();
  const org = useOrganization();

  const ready = org.status === "ready";
  const memberOfOrg = ready && org.organizations.length > 0;
  const active = ready
    ? (org.organizations.find((item) => item.id === org.activeId) ?? null)
    : null;

  const actions = (
    <>
      {memberOfOrg && (
        <select
          aria-label="Organization"
          value={org.activeId ?? ""}
          onChange={(event) => org.select(event.target.value)}
        >
          {org.organizations.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      )}
      <AccountMenu />
    </>
  );

  return (
    <AppLayout actions={actions}>
      <p className="eyebrow">Workspace</p>
      <h1 className="display">Your research workspace</h1>
      <p className="page-lead">Signed in as {account?.email}</p>

      <div className="workspace-grid">
        <section className="card" aria-labelledby="org-card-title">
          <h2 className="card__title" id="org-card-title">
            Active organization
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
          {active !== null && (
            <div className="org-summary">
              <p className="org-summary__name">{active.name}</p>
              <span className="badge">{active.role}</span>
            </div>
          )}
        </section>

        <section className="card" aria-labelledby="next-card-title">
          <h2 className="card__title" id="next-card-title">
            Next up
          </h2>
          <ul className="steps">
            <li className="step step--done">
              <span className="step__marker" aria-hidden="true" />
              Account created
            </li>
            <li className={memberOfOrg ? "step step--done" : "step"}>
              <span className="step__marker" aria-hidden="true" />
              Join an organization
            </li>
            <li className="step">
              <span className="step__marker" aria-hidden="true" />
              Start your first conversation
              <span className="tag">Coming soon</span>
            </li>
          </ul>
        </section>
      </div>
    </AppLayout>
  );
}
