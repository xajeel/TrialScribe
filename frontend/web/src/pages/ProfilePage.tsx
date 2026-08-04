import { useState } from "react";

import { AccountMenu } from "../components/AccountMenu";
import { AppLayout } from "../components/AppLayout";
import { ProfileSettings } from "../components/ProfileSettings";
import { useAuth } from "../auth/useAuth";
import { useOrganization } from "../org/useOrganization";
import {
  profileFixtureFor,
  type ProfileReviewState,
} from "../product/accountAccessReviewFixtures";

export function ProfilePage({
  review,
}: {
  review?: ProfileReviewState;
} = {}) {
  const { account, signOut } = useAuth();
  const organization = useOrganization();
  const fixture = review === undefined ? null : profileFixtureFor(review);
  const [reviewActiveId, setReviewActiveId] = useState(
    fixture?.activeId ?? null,
  );
  const visibleAccount = fixture?.account ?? account;

  if (visibleAccount === null) {
    return (
      <AppLayout>
        <div className="profile-page profile-page--loading" role="status">
          Loading account…
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout actions={review === undefined ? <AccountMenu /> : undefined}>
      <div className="profile-page">
        <ProfileSettings
          account={visibleAccount}
          organizations={fixture?.organizations ?? organization.organizations}
          activeId={fixture === null ? organization.activeId : reviewActiveId}
          organizationStatus={fixture?.organizationStatus ?? organization.status}
          onSelectOrganization={
            fixture === null ? organization.select : setReviewActiveId
          }
          onRetryOrganizations={
            fixture === null ? organization.reload : () => undefined
          }
          onSignOut={review === undefined ? () => void signOut() : () => undefined}
          review={review !== undefined}
          fixtureNote={fixture?.fixtureNote}
        />
      </div>
    </AppLayout>
  );
}
