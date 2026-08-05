import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import {
  EMPTY_REVISION_FILTERS,
  RevisionTimeline,
  type RevisionFiltersValue,
  type RevisionTimelineStatus,
} from "../components/RevisionTimeline";
import { RevisionPreview } from "../components/RevisionPreview";
import {
  RevisionCompare,
  defaultRevisionCompareMode,
  type RevisionCompareMode,
} from "../components/RevisionCompare";
import { RestoreRevisionDialog } from "../components/RestoreRevisionDialog";
import { WorkspaceChrome } from "../components/WorkspaceChrome";
import { useOrganization } from "../org/useOrganization";
import {
  REVISION_REVIEW_COMPARISON,
  REVISION_REVIEW_ROWS,
  revisionRowsForReview,
  revisionViewFromApi,
  type GovernanceReviewState,
  type RevisionComparisonView,
  type RevisionRowView,
} from "../product/governanceReviewFixtures";
import {
  REVIEW_CONVERSATION,
  REVIEW_WORKSPACE_ORGANIZATION,
} from "../product/workspaceReviewFixtures";
import { useProtocolOverview } from "../workspace/useProtocolOverview";
import { useRevisionHistory } from "../workspace/useRevisionHistory";

export type RevisionsReview =
  | "timeline"
  | "preview"
  | "empty"
  | "compare"
  | "restore"
  | "restored";

function reviewState(review: RevisionsReview): GovernanceReviewState {
  return `revisions-${review}`;
}

/** Page 14: immutable section history, preview, and truthful snapshot comparison. */
export function RevisionsPage({ review }: { review?: RevisionsReview } = {}) {
  const { authorizedFetch, account } = useAuth();
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
  const liveConversationId = reviewing ? null : (conversationId ?? null);
  const overview = useProtocolOverview(
    reviewing ? null : (liveOrganization?.id ?? null),
    liveConversationId,
    authorizedFetch,
  );
  const [sectionNumber, setSectionNumber] = useState("");
  const activeSectionNumber = reviewing
    ? "5"
    : sectionNumber || overview.sections[0]?.section_number || null;
  const activeSection = reviewing
    ? null
    : (overview.sections.find(
        (section) => section.section_number === activeSectionNumber,
      ) ?? null);
  const history = useRevisionHistory(
    reviewing ? null : (liveOrganization?.id ?? null),
    liveConversationId,
    activeSectionNumber,
    authorizedFetch,
  );
  const rows = useMemo<ReadonlyArray<RevisionRowView>>(() => {
    if (reviewing) {
      return revisionRowsForReview(reviewState(review));
    }
    return history.revisions.map((revision) =>
      revisionViewFromApi(
        revision,
        activeSection?.current_revision ?? 0,
        account?.id ?? null,
        history.identities,
      ),
    );
  }, [
    account?.id,
    activeSection?.current_revision,
    history.identities,
    history.revisions,
    review,
    reviewing,
  ]);

  const [filters, setFilters] = useState<RevisionFiltersValue>(
    EMPTY_REVISION_FILTERS,
  );
  const [preview, setPreview] = useState<RevisionRowView | null>(() =>
    review === "preview" ? REVISION_REVIEW_ROWS[1] : null,
  );
  const [previewOpener, setPreviewOpener] = useState<HTMLElement | null>(null);
  const [compareRevision, setCompareRevision] = useState<RevisionRowView | null>(
    () =>
      review === "compare" || review === "restore"
        ? REVISION_REVIEW_COMPARISON.earlier
        : null,
  );
  const [compareMode, setCompareMode] = useState<RevisionCompareMode>(
    defaultRevisionCompareMode,
  );
  const [restoreRevision, setRestoreRevision] = useState<RevisionRowView | null>(
    () => (review === "restore" ? REVISION_REVIEW_COMPARISON.earlier : null),
  );
  const [restoreOpener, setRestoreOpener] = useState<HTMLElement | null>(null);
  const [restored, setRestored] = useState(review === "restored");

  const comparison = useMemo<RevisionComparisonView | null>(() => {
    if (compareRevision === null) return null;
    if (reviewing) return REVISION_REVIEW_COMPARISON;
    const current = rows.find((row) => row.current) ?? rows[0] ?? null;
    if (current === null) return null;
    const earlier = compareRevision.current
      ? (rows.find((row) => !row.current) ?? compareRevision)
      : compareRevision;
    return { earlier, later: current };
  }, [compareRevision, reviewing, rows]);

  const timelineStatus: RevisionTimelineStatus = reviewing
    ? "ready"
    : overview.status === "error" || history.status === "error"
      ? "error"
      : overview.status === "ready" &&
          (activeSectionNumber === null || history.status === "ready")
        ? "ready"
        : "loading";
  const protocolTitle = reviewing
    ? REVIEW_CONVERSATION.title
    : (overview.conversation?.title ?? "Protocol workspace");
  const routeConversationId = reviewing
    ? REVIEW_CONVERSATION.id
    : (conversationId ?? "");
  const sectionTitle = reviewing
    ? "5 · Trial Population"
    : activeSection === null
      ? "Protocol revisions"
      : `${activeSection.section_number} · ${activeSection.title}`;

  const openComparison = (revision: RevisionRowView) => {
    setPreview(null);
    setCompareRevision(revision);
  };
  const openRestore = (revision: RevisionRowView, opener: HTMLElement) => {
    setRestoreRevision(revision);
    setRestoreOpener(opener);
  };

  return (
    <div className="protocol-workspace revision-history">
      <a className="protocol-workspace__skip" href="#revision-history-main">
        Skip to main content
      </a>
      <WorkspaceChrome
        conversationId={routeConversationId}
        protocolTitle={protocolTitle}
        organization={organization}
        current="revisions"
        reviewing={reviewing}
      />
      <main id="revision-history-main" className="protocol-workspace__main revision-history__main">
        {comparison === null ? (
          <>
            <header className="revision-history__header">
              <div>
                <p className="protocol-workspace__page-eyebrow">Document history</p>
                <h1>Revision history</h1>
                <p>Review immutable snapshots and compare wording without changing stored content.</p>
              </div>
              <button
                type="button"
                onClick={() => navigate(`/workspace/${encodeURIComponent(routeConversationId)}`)}
              >
                Return to document
              </button>
            </header>
            <div className="revision-history__section-bar">
              <div>
                <span>Section</span>
                <strong>{sectionTitle}</strong>
              </div>
              {!reviewing && overview.sections.length > 0 && (
                <label>
                  <span>Choose section</span>
                  <select
                    value={activeSectionNumber ?? ""}
                    onChange={(event) => {
                      setSectionNumber(event.target.value);
                      setFilters(EMPTY_REVISION_FILTERS);
                      setPreview(null);
                    }}
                  >
                    {overview.sections.map((section) => (
                      <option key={section.id} value={section.section_number}>
                        {section.section_number} · {section.title}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
            {reviewing && (
              <p className="revision-history__review-note">
                Development review data — restore demonstrations do not change stored protocol content.
              </p>
            )}
            {restored && (
              <p className="revision-history__feedback" role="status">
                Revision 6 is shown as revision 8 in this review demonstration. Stored history was not changed.
              </p>
            )}
            <RevisionTimeline
              status={timelineStatus}
              rows={rows}
              filters={filters}
              onFiltersChange={setFilters}
              onPreview={(revision, opener) => {
                setPreview(revision);
                setPreviewOpener(opener);
              }}
              onCompare={rows.length > 1 ? openComparison : undefined}
              onRetry={() => {
                overview.retry();
                history.retry();
              }}
              onReturnToDocument={() =>
                navigate(`/workspace/${encodeURIComponent(routeConversationId)}`)
              }
            />
            <RevisionPreview
              revision={preview}
              returnFocusTo={previewOpener}
              onClose={() => setPreview(null)}
              onCompare={rows.length > 1 ? openComparison : undefined}
              onRestore={reviewing ? openRestore : undefined}
            />
          </>
        ) : (
          <RevisionCompare
            comparison={comparison}
            mode={compareMode}
            onModeChange={setCompareMode}
            onBack={() => setCompareRevision(null)}
            onKeepCurrent={() => setCompareRevision(null)}
            onRestore={
              reviewing
                ? (opener) => openRestore(comparison.earlier, opener)
                : undefined
            }
          />
        )}
      </main>
      {restoreRevision !== null && (
        <RestoreRevisionDialog
          open
          revision={restoreRevision}
          newRevisionNumber={8}
          returnFocusTo={restoreOpener}
          onCancel={() => setRestoreRevision(null)}
          onConfirm={() => {
            setRestoreRevision(null);
            setCompareRevision(null);
            setRestored(true);
          }}
        />
      )}
    </div>
  );
}
