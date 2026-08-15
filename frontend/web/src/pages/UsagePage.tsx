import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/AsyncState";
import {
  DEFAULT_USAGE_FILTERS,
  GenerationUsageTable,
  type UsageFiltersValue,
} from "../components/GenerationUsageTable";
import { UsageSummary } from "../components/UsageSummary";
import { useOrganization } from "../org/useOrganization";
import {
  REVIEW_USAGE_EMPTY,
  REVIEW_USAGE_RUNNING,
  REVIEW_USAGE_VIEW,
  type UsageView,
} from "../product/deliveryAuditReviewFixtures";
import { REVIEW_CONVERSATION } from "../product/workspaceReviewFixtures";
import { useProtocolOverview } from "../workspace/useProtocolOverview";
import {
  USAGE_LOAD_ERROR,
  useProtocolUsage,
} from "../workspace/useProtocolUsage";

export type UsageReviewState =
  | "populated"
  | "expanded"
  | "running"
  | "empty"
  | "error"
  | "filtered";

function UsageBackdrop({ protocolTitle }: { protocolTitle: string }) {
  return (
    <div className="delivery-backdrop" aria-hidden="true">
      <header>
        <strong>TrialScribe</strong>
        <span>Protocols</span>
        <span>Workspace</span>
        <span>Review</span>
      </header>
      <main>
        <p>Protocol workspace</p>
        <h2>{protocolTitle}</h2>
        <div className="delivery-backdrop__columns">
          <div />
          <div />
          <div />
        </div>
      </main>
    </div>
  );
}
function usageForReview(review: UsageReviewState): UsageView {
  if (review === "empty" || review === "error") return REVIEW_USAGE_EMPTY;
  if (review === "running") return REVIEW_USAGE_RUNNING;
  return REVIEW_USAGE_VIEW;
}

/** Page 17: protocol-scoped provider usage without cross-workspace claims. */
export function UsagePage({
  review,
}: {
  review?: UsageReviewState;
} = {}) {
  const { authorizedFetch } = useAuth();
  const org = useOrganization();
  const navigate = useNavigate();
  const { conversationId } = useParams();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const reviewing = review !== undefined;
  const liveOrganization =
    org.status === "ready"
      ? (org.organizations.find((item) => item.id === org.activeId) ?? null)
      : null;
  const overview = useProtocolOverview(
    reviewing ? null : (liveOrganization?.id ?? null),
    reviewing ? null : (conversationId ?? null),
    authorizedFetch,
  );
  const usage = useProtocolUsage({
    organizationId: reviewing ? null : (liveOrganization?.id ?? null),
    conversationId: reviewing ? null : (conversationId ?? null),
    fetcher: authorizedFetch,
    enabled: !reviewing,
  });
  const [filters, setFilters] = useState<UsageFiltersValue>(() =>
    review === "filtered"
      ? { ...DEFAULT_USAGE_FILTERS, outcome: "attention" }
      : DEFAULT_USAGE_FILTERS,
  );
  const [reviewError, setReviewError] = useState(review === "error");
  const [feedback, setFeedback] = useState<string | null>(null);
  const routeConversationId = reviewing
    ? REVIEW_CONVERSATION.id
    : (conversationId ?? "");
  const protocolTitle = reviewing
    ? REVIEW_CONVERSATION.title
    : (usage.view?.protocolTitle ??
      overview.conversation?.title ??
      "Protocol workspace");
  const view = reviewing ? usageForReview(review) : usage.view;

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <div className="delivery-page usage-page">
      <UsageBackdrop protocolTitle={protocolTitle} />
      <aside
        className="delivery-sheet usage-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="usage-sheet-title"
      >
        <header className="delivery-sheet__header">
          <div>
            <p className="delivery-sheet__eyebrow">
              {reviewing ? "AURORA-301 — Phase III" : protocolTitle}
            </p>
            <h1 id="usage-sheet-title" ref={headingRef} tabIndex={-1}>
              Usage and cost
            </h1>
            <p>Only model activity in this protocol workspace.</p>
          </div>
          <button
            type="button"
            onClick={() =>
              navigate(`/workspace/${encodeURIComponent(routeConversationId)}`)
            }
            aria-label="Close usage and cost"
          >
            ×
          </button>
        </header>

        {feedback !== null && (
          <p className="delivery-sheet__feedback" role="status">
            {feedback}
          </p>
        )}

        {!reviewing && usage.loading && view === null && (
          <div className="delivery-sheet__state">
            <LoadingState label="Loading workspace usage…" />
          </div>
        )}
        {!reviewing && overview.status === "error" && (
          <div className="delivery-sheet__state">
            <ErrorState
              message="Could not load this workspace."
              onRetry={overview.retry}
            />
          </div>
        )}
        {!reviewing && overview.status !== "error" && usage.error && (
          <div className="delivery-sheet__state">
            <ErrorState message={USAGE_LOAD_ERROR} onRetry={usage.retry} />
          </div>
        )}

        {view !== null && (
          <div className="delivery-sheet__body">
            <UsageSummary view={view} />
            {view.fixtureNote !== undefined && (
              <p className="delivery-sheet__fixture">{view.fixtureNote}</p>
            )}
            <GenerationUsageTable
              view={view}
              filters={filters}
              onFiltersChange={(next) => {
                setFilters(next);
                if (reviewing) {
                  setFeedback(
                    "Filters changed locally for this development review only.",
                  );
                }
              }}
              initialExpandedId={
                review === "expanded" ? view.generations[0]?.id : undefined
              }
              error={reviewError}
              onRetry={() => {
                setReviewError(false);
                setFeedback(
                  "Retry completed in this development review. No stored usage was read or changed.",
                );
              }}
            />
          </div>
        )}
      </aside>
    </div>
  );
}
