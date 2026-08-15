import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/AsyncState";
import { ReadinessSummary } from "../components/ReadinessSummary";
import {
  ReadinessTable,
  type ReadinessFilter,
} from "../components/ReadinessTable";
import { WorkspaceChrome } from "../components/WorkspaceChrome";
import { useOrganization } from "../org/useOrganization";
import {
  readinessForReview,
  type GovernanceReviewState,
  type ReadinessIssueView,
  type ReadinessView,
} from "../product/governanceReviewFixtures";
import {
  REVIEW_CONVERSATION,
  REVIEW_WORKSPACE_ORGANIZATION,
} from "../product/workspaceReviewFixtures";
import { useProtocolReadiness } from "../workspace/useProtocolReadiness";

export type ReadinessReview =
  | "incomplete"
  | "attention"
  | "filtered"
  | "ready"
  | "retry";

function reviewState(review: ReadinessReview): GovernanceReviewState {
  return `readiness-${review}`;
}

/** Page 15: stored protocol readiness snapshot, or a local review fixture. */
export function ReadinessPage({ review }: { review?: ReadinessReview } = {}) {
  const { authorizedFetch } = useAuth();
  const org = useOrganization();
  const navigate = useNavigate();
  const { conversationId } = useParams();
  const reviewing = review !== undefined;
  const liveOrganization =
    org.status === "ready"
      ? (org.organizations.find((item) => item.id === org.activeId) ?? null)
      : null;
  const organization = reviewing
    ? REVIEW_WORKSPACE_ORGANIZATION
    : liveOrganization;
  const readiness = useProtocolReadiness({
    organizationId: reviewing ? null : (liveOrganization?.id ?? null),
    conversationId: reviewing ? null : (conversationId ?? null),
    fetcher: authorizedFetch,
    enabled: !reviewing && liveOrganization !== null,
  });
  const [reviewData, setReviewData] = useState<ReadinessView | null>(() =>
    review === undefined ? null : readinessForReview(reviewState(review)),
  );
  const [filter, setFilter] = useState<ReadinessFilter>(() =>
    review === "filtered" || review === "attention" ? "attention" : "all",
  );
  const [feedback, setFeedback] = useState<string | null>(null);
  const data = reviewing ? reviewData : readiness.view;
  const routeConversationId = reviewing
    ? REVIEW_CONVERSATION.id
    : (conversationId ?? "");
  const protocolTitle = reviewing
    ? REVIEW_CONVERSATION.title
    : (readiness.record?.protocol_title ?? "Protocol workspace");

  const navigateToSection = (sectionNumber: string) =>
    navigate(
      `/workspace/${encodeURIComponent(routeConversationId)}?section=${encodeURIComponent(sectionNumber)}`,
    );
  const handleIssue = (issue: ReadinessIssueView) => {
    if (issue.action === "view-sources") {
      navigate(`/workspace/${encodeURIComponent(routeConversationId)}/sources`);
      return;
    }
    if (issue.action === "open-section" && issue.sectionNumber !== undefined) {
      navigateToSection(issue.sectionNumber);
      return;
    }
    if (issue.action === "retry-check") {
      void readiness.start();
      return;
    }
    if (!reviewing) return;
    if (issue.action === "retry-demo") {
      setReviewData((current) =>
        current === null
          ? current
          : {
              ...current,
              issues: current.issues.map((item) =>
                item.id === issue.id
                  ? { ...item, state: "resolved", actionLabel: undefined }
                  : item,
              ),
              sections: current.sections.map((section) => ({
                ...section,
                issues: section.issues.map((item) =>
                  item.id === issue.id
                    ? { ...item, state: "resolved", actionLabel: undefined }
                    : item,
                ),
              })),
            },
      );
      setFeedback(
        "Retry completed in this development review. Stored protocol content was not changed.",
      );
      return;
    }
    setFeedback(
      "This development review action is illustrative and did not change stored protocol content.",
    );
  };

  return (
    <div className="protocol-workspace readiness-review">
      <a className="protocol-workspace__skip" href="#readiness-review-main">
        Skip to main content
      </a>
      <WorkspaceChrome
        conversationId={routeConversationId}
        protocolTitle={protocolTitle}
        organization={organization}
        current="readiness"
        reviewing={reviewing}
      />
      <main id="readiness-review-main" className="protocol-workspace__main readiness-review__main">
        <header className="readiness-review__header">
          <div>
            <p className="protocol-workspace__page-eyebrow">Editorial review</p>
            <h1>Protocol readiness</h1>
            <p>Check current section and source facts before preparing an export.</p>
          </div>
          <div>
            {!reviewing && (
              <button
                type="button"
                disabled={readiness.pending || readiness.loading}
                onClick={() => void readiness.start()}
              >
                {readiness.record?.checked === true ? "Check again" : "Check protocol"}
              </button>
            )}
            <button
              type="button"
              onClick={() => navigate(`/workspace/${encodeURIComponent(routeConversationId)}`)}
            >
              Return to workspace
            </button>
          </div>
        </header>
        {!reviewing && readiness.loading && (
          <section className="readiness-review__state" aria-label="Protocol readiness">
            <LoadingState label="Loading protocol readiness…" />
          </section>
        )}
        {!reviewing && readiness.error !== null && (
          <section className="readiness-review__state" aria-label="Protocol readiness">
            <ErrorState
              message={readiness.error}
              onRetry={readiness.retry}
            />
          </section>
        )}
        {feedback !== null && (
          <p className="readiness-review__feedback" role="status">
            {feedback}
          </p>
        )}
        {data !== null && (
          <>
            <ReadinessSummary data={data} />
            <ReadinessTable
              data={data}
              filter={filter}
              onFilterChange={setFilter}
              onIssueAction={handleIssue}
              onOpenSection={(section) => navigateToSection(section.sectionNumber)}
              onOpenEditor={(section) => navigateToSection(section.sectionNumber)}
              onViewHistory={(section) =>
                navigate(
                  `/workspace/${encodeURIComponent(routeConversationId)}/revisions?section=${encodeURIComponent(section.sectionNumber)}`,
                )
              }
              checking={readiness.pending}
            />
          </>
        )}
      </main>
    </div>
  );
}
