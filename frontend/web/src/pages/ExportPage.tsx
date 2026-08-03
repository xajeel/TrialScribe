import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/AsyncState";
import {
  ExportJobPanel,
  type ExportJobPanelState,
} from "../components/ExportJobPanel";
import {
  ExportContentSummary,
  ExportProtocolSummary,
  ExportScopeSelector,
} from "../components/ExportScopeSelector";
import { SectionManifest } from "../components/SectionManifest";
import { useOrganization } from "../org/useOrganization";
import {
  REVIEW_EXPORT_EMPTY,
  REVIEW_EXPORT_JOB,
  REVIEW_EXPORT_VIEW,
  exportViewFromWorkspace,
  type ExportFileView,
  type ExportReviewState,
  type ExportScope,
} from "../product/deliveryAuditReviewFixtures";
import { REVIEW_CONVERSATION } from "../product/workspaceReviewFixtures";
import { useProtocolOverview } from "../workspace/useProtocolOverview";

function ReviewBackdrop({ protocolTitle }: { protocolTitle: string }) {
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
function initialPanelState(
  review: ExportReviewState | undefined,
): "configuration" | ExportJobPanelState {
  if (review === "building" || review === "ready" || review === "failed") {
    return review;
  }
  return "configuration";
}

/** Page 16: exact export scope plus honest local/review job states. */
export function ExportPage({
  review,
}: {
  review?: ExportReviewState;
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
  const [scope, setScope] = useState<ExportScope>(() =>
    review === "drafts" ? "include-drafts" : "done-only",
  );
  const [panelState, setPanelState] = useState<
    "configuration" | ExportJobPanelState
  >(() => initialPanelState(review));
  const [feedback, setFeedback] = useState<string | null>(null);
  const routeConversationId = reviewing
    ? REVIEW_CONVERSATION.id
    : (conversationId ?? "");
  const reviewView = review === "empty" ? REVIEW_EXPORT_EMPTY : REVIEW_EXPORT_VIEW;
  const view = reviewing
    ? reviewView
    : overview.conversation === null
      ? null
      : exportViewFromWorkspace(overview.conversation, overview.sections);
  const protocolTitle = reviewing
    ? REVIEW_CONVERSATION.title
    : (overview.conversation?.title ?? "Protocol workspace");

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  const close = () => {
    navigate(`/workspace/${encodeURIComponent(routeConversationId)}`);
  };
  const handleDownload = (file: ExportFileView) => {
    if (!reviewing) return;
    setFeedback(
      `${file.filename} was not downloaded. This is a development review demonstration.`,
    );
  };
  const handleGenerate = () => {
    if (!reviewing || view === null || view.doneSections === 0) return;
    setFeedback(
      "Development review only — no export job was created or persisted.",
    );
    setPanelState("building");
  };

  return (
    <div className="delivery-page export-page">
      <ReviewBackdrop protocolTitle={protocolTitle} />
      <aside
        className="delivery-sheet export-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-sheet-title"
      >
        <header className="delivery-sheet__header">
          <div>
            <p className="delivery-sheet__eyebrow">
              {reviewing ? "AURORA-301 — Phase III" : protocolTitle}
            </p>
            <h1 id="export-sheet-title" ref={headingRef} tabIndex={-1}>
              Export protocol
            </h1>
            <p>
              Create an ordered ICH M11 Microsoft Word document from this
              workspace.
            </p>
          </div>
          <button type="button" onClick={close} aria-label="Close export">
            ×
          </button>
        </header>

        {feedback !== null && (
          <p className="delivery-sheet__feedback" role="status">
            {feedback}
          </p>
        )}

        {!reviewing && overview.status === "loading" && (
          <div className="delivery-sheet__state">
            <LoadingState label="Loading export options…" />
          </div>
        )}
        {!reviewing && overview.status === "error" && (
          <div className="delivery-sheet__state">
            <ErrorState
              message="Could not load export options."
              onRetry={overview.retry}
            />
          </div>
        )}

        {view !== null && panelState === "configuration" && (
          <>
            <div className="delivery-sheet__body">
              <ExportProtocolSummary view={view} />
              <ExportScopeSelector
                view={view}
                scope={scope}
                onScopeChange={setScope}
              />
              <SectionManifest sections={view.sections} scope={scope} />
              <ExportContentSummary view={view} scope={scope} />
              {view.doneSections === 0 ? (
                <div className="export-page__unavailable" role="status">
                  <strong>Complete at least one section before exporting.</strong>
                  <button
                    type="button"
                    onClick={() =>
                      navigate(
                        `/workspace/${encodeURIComponent(routeConversationId)}/readiness`,
                      )
                    }
                  >
                    Review sections
                  </button>
                </div>
              ) : !reviewing ? (
                <p className="export-page__unavailable" role="status">
                  Export generation is not connected yet. You can inspect the
                  current document scope here without changing protocol content.
                </p>
              ) : null}
              {view.fixtureNote !== undefined && (
                <p className="delivery-sheet__fixture">{view.fixtureNote}</p>
              )}
            </div>
            <footer className="delivery-sheet__footer">
              <button type="button" onClick={close}>Cancel</button>
              <button
                className="delivery-button--primary"
                type="button"
                disabled={!reviewing || view.doneSections === 0}
                onClick={handleGenerate}
              >
                Generate DOCX
              </button>
            </footer>
          </>
        )}

        {panelState !== "configuration" && (
          <div className="delivery-sheet__body delivery-sheet__body--job">
            <ExportJobPanel
              state={panelState}
              job={REVIEW_EXPORT_JOB}
              onClose={close}
              onRetry={() => {
                setFeedback("Retry started in this development review only.");
                setPanelState("building");
              }}
              onBack={() => {
                setFeedback(null);
                setPanelState("configuration");
              }}
              onCreateAnother={() => {
                setFeedback(null);
                setPanelState("configuration");
              }}
              onDownload={handleDownload}
            />
          </div>
        )}
      </aside>
    </div>
  );
}
