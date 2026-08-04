import { useState } from "react";
import { useParams } from "react-router-dom";

import type { DocumentRecord } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { AddSourceSheet } from "../components/AddSourceSheet";
import { ErrorState, LoadingState } from "../components/AsyncState";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { SourceList } from "../components/SourceList";
import { WorkspaceChrome } from "../components/WorkspaceChrome";
import { useOrganization } from "../org/useOrganization";
import { useAuthoringWorkspace } from "../workspace/useAuthoringWorkspace";
import {
  reviewSources,
  type SourcesReview,
} from "../product/workbenchReviewFixtures";
import { REVIEW_WORKSPACE_ORGANIZATION } from "../product/workspaceReviewFixtures";

/** The trial data and research documents attached to one protocol. */
export function SourceLibraryPage({
  review,
}: {
  review?: SourcesReview;
} = {}) {
  const { authorizedFetch } = useAuth();
  const org = useOrganization();
  const { conversationId } = useParams();
  const [sheetOpen, setSheetOpen] = useState(false);
  const [sheetOpener, setSheetOpener] = useState<HTMLElement | null>(null);
  const [pendingRemoval, setPendingRemoval] = useState<DocumentRecord | null>(
    null,
  );
  const [removalOpener, setRemovalOpener] = useState<HTMLElement | null>(null);

  const reviewing = review !== undefined;
  const liveActive =
    org.status === "ready"
      ? (org.organizations.find((item) => item.id === org.activeId) ?? null)
      : null;
  const organization = reviewing ? REVIEW_WORKSPACE_ORGANIZATION : liveActive;

  const live = useAuthoringWorkspace(
    reviewing ? null : (liveActive?.id ?? null),
    authorizedFetch,
    reviewing ? null : (conversationId ?? null),
  );
  const sample = reviewing ? reviewSources(review) : null;
  const workspace = sample ?? live;

  const title = workspace.selectedConversation?.title ?? "Protocol workspace";
  const archived = workspace.selectedConversation?.status === "archived";
  const busy = workspace.action !== "idle";
  const total = workspace.documents.length;

  const confirmRemoval = async () => {
    if (pendingRemoval === null) {
      return;
    }
    await workspace.removeDocument(pendingRemoval.id);
    setPendingRemoval(null);
  };

  return (
    <div className="protocol-workspace source-library">
      <a className="protocol-workspace__skip" href="#protocol-workspace-main">
        Skip to main content
      </a>

      <WorkspaceChrome
        conversationId={
          conversationId ?? workspace.selectedConversation?.id ?? ""
        }
        protocolTitle={title}
        organization={organization}
        current="sources"
        reviewing={reviewing}
      />

      <main id="protocol-workspace-main" className="protocol-workspace__main">
        <div className="protocol-workspace__page-header source-library__header">
          <div>
            <p className="protocol-workspace__page-eyebrow">
              Evidence for drafting
            </p>
            <h1>Source library</h1>
            <p className="protocol-workspace__lede">
              {total === 0
                ? "Trial data and research documents attached to this protocol."
                : `${total} ${total === 1 ? "source" : "sources"} attached to this protocol.`}
            </p>
          </div>
          {!archived && (
            <button
              type="button"
              className="source-library__add"
              disabled={busy}
              onClick={(event) => {
                setSheetOpener(event.currentTarget);
                setSheetOpen(true);
              }}
            >
              Add source
            </button>
          )}
        </div>

        {workspace.workspaceStatus === "loading" && (
          <section className="protocol-workspace__state" aria-label="Sources">
            <LoadingState label="Loading this protocol's sources…" />
          </section>
        )}

        {workspace.workspaceStatus === "error" && (
          <section className="protocol-workspace__state" aria-label="Sources">
            <ErrorState
              message="Could not load this protocol's sources."
              onRetry={workspace.retryWorkspace}
            />
          </section>
        )}

        {workspace.workspaceStatus === "ready" && (
          <>
            {workspace.feedback !== null && (
              <p
                className={
                  workspace.feedback.kind === "error"
                    ? "protocol-workspace__feedback protocol-workspace__feedback--error"
                    : "protocol-workspace__feedback"
                }
                role={workspace.feedback.kind === "error" ? "alert" : "status"}
              >
                {workspace.feedback.message}
              </p>
            )}

            {total === 0 ? (
              <section
                className="source-library__empty"
                aria-labelledby="source-library-empty-title"
              >
                <h2 id="source-library-empty-title">No sources added</h2>
                <p>
                  Add trial JSON or a PDF, TXT, or MD research document to give
                  drafting something to cite.
                </p>
                {!archived && (
                  <button
                    type="button"
                    className="source-library__add"
                    disabled={busy}
                    onClick={(event) => {
                      setSheetOpener(event.currentTarget);
                      setSheetOpen(true);
                    }}
                  >
                    Add source
                  </button>
                )}
              </section>
            ) : (
              <SourceList
                documents={workspace.documents}
                busy={busy}
                onRemove={
                  archived
                    ? undefined
                    : (record, opener) => {
                        setPendingRemoval(record);
                        setRemovalOpener(opener);
                      }
                }
              />
            )}

            {archived && (
              <p className="protocol-workspace__archived" role="status">
                This protocol is archived. Restore it from the library to change
                its sources.
              </p>
            )}
          </>
        )}
      </main>

      <AddSourceSheet
        open={sheetOpen}
        pending={workspace.action === "uploading"}
        returnFocusTo={sheetOpener}
        onUpload={workspace.upload}
        onClose={() => setSheetOpen(false)}
      />

      <ConfirmDialog
        open={pendingRemoval !== null}
        title="Remove this source?"
        description={
          pendingRemoval === null
            ? ""
            : `${pendingRemoval.filename} will be deleted from this protocol. This cannot be undone.`
        }
        confirmLabel="Remove source"
        pending={workspace.action === "removing"}
        destructive
        returnFocusTo={removalOpener}
        onConfirm={() => void confirmRemoval()}
        onCancel={() => setPendingRemoval(null)}
      />
    </div>
  );
}
