import { useEffect, useMemo, useState } from "react";

import type { M11Section } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { AccountMenu } from "../components/AccountMenu";
import { AppLayout } from "../components/AppLayout";
import { AuthoringPane } from "../components/AuthoringPane";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/AsyncState";
import { ConversationPane } from "../components/ConversationPane";
import { OrganizationOnboarding } from "../components/OrganizationOnboarding";
import { ResourcePane } from "../components/ResourcePane";
import { SectionModal } from "../components/SectionModal";
import { useOrganization } from "../org/useOrganization";
import { useAuthoringWorkspace } from "../workspace/useAuthoringWorkspace";

export function DashboardPage() {
  const { account, authorizedFetch } = useAuth();
  const org = useOrganization();
  const [modalSectionId, setModalSectionId] = useState<string | null>(null);
  const [modalOpener, setModalOpener] = useState<HTMLElement | null>(null);

  const ready = org.status === "ready";
  const memberOfOrg = ready && org.organizations.length > 0;
  const active = ready
    ? (org.organizations.find((item) => item.id === org.activeId) ?? null)
    : null;
  const workspace = useAuthoringWorkspace(active?.id ?? null, authorizedFetch);
  const modalSection = useMemo(
    () =>
      workspace.sections.find((item) => item.id === modalSectionId) ?? null,
    [modalSectionId, workspace.sections],
  );

  useEffect(() => {
    setModalSectionId(null);
    setModalOpener(null);
  }, [workspace.selectedConversationId]);

  const openSection = (section: M11Section, opener: HTMLElement) => {
    setModalSectionId(section.id);
    setModalOpener(opener);
  };

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
      <div className="authoring-workspace-page">
        <p className="workspace-session">Signed in as {account?.email}</p>
        {org.status !== "ready" && (
          <section className="workspace-entry-state" aria-label="Organizations">
            {org.status === "error" ? (
              <ErrorState
                message="Could not load your organizations."
                onRetry={org.reload}
              />
            ) : (
              <LoadingState label="Loading your organizations…" />
            )}
          </section>
        )}
        {ready && !memberOfOrg && (
          <section className="workspace-entry-state" aria-label="Organizations">
            <EmptyState
              title="No organizations yet"
              description="Create your first organization or join one with an invitation."
            />
            <OrganizationOnboarding />
          </section>
        )}
        {active !== null && (
          <>
            <div className="authoring-workspace">
              <ConversationPane workspace={workspace} />
              <AuthoringPane workspace={workspace} />
              <ResourcePane
                workspace={workspace}
                onOpenSection={openSection}
              />
            </div>
            <SectionModal
              section={modalSection}
              returnFocusTo={modalOpener}
              onClose={() => {
                setModalSectionId(null);
                setModalOpener(null);
              }}
            />
          </>
        )}
        {ready && memberOfOrg && active === null && (
          <section className="workspace-entry-state" aria-label="Organizations">
            <LoadingState label="Loading your organizations…" />
          </section>
        )}
      </div>
    </AppLayout>
  );
}
