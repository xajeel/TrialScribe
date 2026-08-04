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
  readinessFromWorkspace,
  type GovernanceReviewState,
  type ReadinessIssueView,
  type ReadinessView,
} from "../product/governanceReviewFixtures";
import {
  REVIEW_CONVERSATION,
  REVIEW_WORKSPACE_ORGANIZATION,
} from "../product/workspaceReviewFixtures";
import { useProtocolOverview } from "../workspace/useProtocolOverview";

export type ReadinessReview =
  | "incomplete"
  | "attention"
  | "filtered"
  | "ready"
  | "retry";

function reviewState(review: ReadinessReview): GovernanceReviewState {
  return `readiness-${review}`;
}

/** Page 15: factual editorial readiness over current sections and sources. */
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
  const overview = useProtocolOverview(
    reviewing ? null : (liveOrganization?.id ?? null),
    reviewing ? null : (conversationId ?? null),
    authorizedFetch,
  );
  const [reviewData, setReviewData] = useState<ReadinessView | null>(() =>
    review === undefined ? null : readinessForReview(reviewState(review)),
  );
  const [filter, setFilter] = useState<ReadinessFilter>(() =>
    review === "filtered" || review === "attention" ? "attention" : "all",
  );
  const [feedback, setFeedback] = useState<string | null>(null);
  const data = reviewing
    ? reviewData
    : overview.conversation === null
      ? null
      : readinessFromWorkspace(
          overview.conversation,
          overview.sections,
          overview.documents,
        );
  const routeConversationId = reviewing
    ? REVIEW_CONVERSATION.id
    : (conversationId ?? "");
  const protocolTitle = reviewing
    ? REVIEW_CONVERSATION.title
    : (overview.conversation?.title ?? "Protocol workspace");

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
          <button
            type="button"
            onClick={() => navigate(`/workspace/${encodeURIComponent(routeConversationId)}`)}
          >
            Return to workspace
          </button>
        </header>
        {!reviewing && overview.status === "loading" && (
          <section className="readiness-review__state" aria-label="Protocol readiness">
            <LoadingState label="Loading protocol readiness…" />
          </section>
        )}
        {!reviewing && overview.status === "error" && (
          <section className="readiness-review__state" aria-label="Protocol readiness">
            <ErrorState
              message="Could not load protocol readiness."
              onRetry={overview.retry}
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
            />
          </>
        )}
      </main>
    </div>
  );
}
