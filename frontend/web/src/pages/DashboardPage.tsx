import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import type { M11Section } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { AccountMenu } from "../components/AccountMenu";
import { AuthoringPane } from "../components/AuthoringPane";
import { ErrorState, LoadingState } from "../components/AsyncState";
import { BrandLogo } from "../components/BrandLogo";
import { ConversationPane } from "../components/ConversationPane";
import { ResourcePane } from "../components/ResourcePane";
import { SectionReader } from "../components/SectionReader";
import { useOrganization } from "../org/useOrganization";
import { useAuthoringWorkspace } from "../workspace/useAuthoringWorkspace";
import {
  reviewWorkbench,
  type WorkbenchReview,
} from "../product/workbenchReviewFixtures";
import { REVIEW_WORKSPACE_ORGANIZATION } from "../product/workspaceReviewFixtures";
import { OrganizationSetupPage } from "./OrganizationSetupPage";

type Pane = "protocols" | "resources";

/** The three-pane authoring workbench: protocols, the section document, resources. */
export function DashboardPage({
  review,
}: {
  review?: WorkbenchReview;
} = {}) {
  const { authorizedFetch } = useAuth();
  const org = useOrganization();
  const { conversationId } = useParams();
  const [readerSectionId, setReaderSectionId] = useState<string | null>(null);
  const [readerOpener, setReaderOpener] = useState<HTMLElement | null>(null);
  const [openPane, setOpenPane] = useState<Pane | null>(null);

  const reviewing = review !== undefined;
  const ready = org.status === "ready";
  const memberOfOrg = ready && org.organizations.length > 0;
  const liveActive = ready
    ? (org.organizations.find((item) => item.id === org.activeId) ?? null)
    : null;
  const organization = reviewing ? REVIEW_WORKSPACE_ORGANIZATION : liveActive;

  const live = useAuthoringWorkspace(
    reviewing ? null : (liveActive?.id ?? null),
    authorizedFetch,
    reviewing ? null : (conversationId ?? null),
  );
  const sample = reviewing ? reviewWorkbench(review) : null;
  const workspace = sample ?? live;

  const readerSection = useMemo(
    () => workspace.sections.find((item) => item.id === readerSectionId) ?? null,
    [readerSectionId, workspace.sections],
  );

  useEffect(() => {
    setReaderSectionId(null);
    setReaderOpener(null);
  }, [workspace.selectedConversationId]);

  useEffect(() => {
    if (openPane === null) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpenPane(null);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openPane]);

  const openSection = useCallback(
    (section: M11Section, opener: HTMLElement) => {
      setReaderSectionId(section.id);
      setReaderOpener(opener);
      setOpenPane(null);
    },
    [],
  );

  const closeReader = useCallback(() => {
    setReaderSectionId(null);
    setReaderOpener(null);
  }, []);

  if (ready && !memberOfOrg && !reviewing) {
    return <OrganizationSetupPage />;
  }

  const protocol = workspace.selectedConversation;
  const routeId = conversationId ?? protocol?.id ?? "";
  const saving = workspace.action === "saving";

  return (
    <div className="workbench">
      <a className="workbench__skip" href="#workbench-centre">
        Skip to main content
      </a>

      <header className="workbench__topbar">
        <div className="workbench__brand">
          <BrandLogo
            className="workbench__logo"
            to="/protocols"
            ariaLabel="TrialScribe protocols"
          />
          <span className="workbench__divider" aria-hidden="true" />
          <span className="workbench__org">{organization?.name ?? ""}</span>
          <span className="workbench__slash" aria-hidden="true">
            /
          </span>
          <span className="workbench__protocol">
            {protocol?.title ?? "Protocol workspace"}
          </span>
          {protocol !== null && (
            <span
              className={
                protocol.status === "archived"
                  ? "workbench-badge"
                  : "workbench-badge workbench-badge--active"
              }
            >
              {protocol.status === "archived" ? "Archived" : "Active"}
            </span>
          )}
        </div>

        <div className="workbench__topbar-actions">
          <span className="workbench__saved" role="status">
            {saving ? "Saving…" : "Saved"}
          </span>
          {routeId !== "" && (
            <nav className="workbench__links" aria-label="Protocol views">
              <Link to={`/workspace/${encodeURIComponent(routeId)}/instructions`}>
                Instructions
              </Link>
              <Link to={`/workspace/${encodeURIComponent(routeId)}/progress`}>
                Progress
              </Link>
              <Link to={`/workspace/${encodeURIComponent(routeId)}/sources`}>
                Sources
              </Link>
            </nav>
          )}
          {reviewing ? (
            <span className="avatar" aria-label="Review account MC">
              MC
            </span>
          ) : (
            <AccountMenu />
          )}
        </div>
      </header>

      <div className="workbench__toolbar">
        <button
          type="button"
          className="workbench__toggle"
          aria-expanded={openPane === "protocols"}
          onClick={() =>
            setOpenPane((current) =>
              current === "protocols" ? null : "protocols",
            )
          }
        >
          Protocols
        </button>
        <button
          type="button"
          className="workbench__toggle"
          aria-expanded={openPane === "resources"}
          onClick={() =>
            setOpenPane((current) =>
              current === "resources" ? null : "resources",
            )
          }
        >
          Outline &amp; sources
        </button>
      </div>

      {!reviewing && org.status !== "ready" && (
        <section className="workbench__state" aria-label="Organizations">
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

      {(reviewing || liveActive !== null) && (
        <>
          {openPane !== null && (
            <button
              type="button"
              className="workbench__scrim"
              aria-label="Close panel"
              onClick={() => setOpenPane(null)}
            />
          )}

          <div
            className={
              openPane === null
                ? "workbench__body"
                : `workbench__body workbench__body--open-${openPane}`
            }
          >
            <div className="workbench__pane workbench__pane--rail">
              <ConversationPane workspace={workspace} />
            </div>
            <div className="workbench__pane workbench__pane--centre">
              <div id="workbench-centre">
                <AuthoringPane workspace={workspace} />
              </div>
            </div>
            <div className="workbench__pane workbench__pane--inspector">
              <ResourcePane workspace={workspace} onOpenSection={openSection} />
            </div>
          </div>

          <SectionReader
            section={readerSection}
            returnFocusTo={readerOpener}
            onOpenInEditor={(section) => {
              workspace.selectSection(section.section_number);
              closeReader();
            }}
            onAddInstruction={(section) => {
              workspace.selectSection(section.section_number);
              closeReader();
            }}
            onClose={closeReader}
            inspectCitations={
              reviewing || liveActive === null || workspace.selectedConversationId === null
                ? undefined
                : {
                    fetcher: authorizedFetch,
                    organizationId: liveActive.id,
                    conversationId: workspace.selectedConversationId,
                  }
            }
          />
        </>
      )}

      {ready && memberOfOrg && liveActive === null && !reviewing && (
        <section className="workbench__state" aria-label="Organizations">
          <LoadingState label="Loading your organizations…" />
        </section>
      )}
    </div>
  );
}
