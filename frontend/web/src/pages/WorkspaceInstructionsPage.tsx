import { useParams } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/AsyncState";
import { GenerationPanel } from "../components/GenerationPanel";
import { InstructionComposer } from "../components/InstructionComposer";
import { InstructionTimeline } from "../components/InstructionTimeline";
import { WorkspaceChrome } from "../components/WorkspaceChrome";
import { useOrganization } from "../org/useOrganization";
import { useProtocolOverview } from "../workspace/useProtocolOverview";
import {
  REVIEW_WORKSPACE_ORGANIZATION,
  reviewOverview,
  type InstructionsReview,
} from "../product/workspaceReviewFixtures";

/** The protocol's durable writing instructions and the drafting capability panel. */
export function WorkspaceInstructionsPage({
  review,
}: {
  review?: InstructionsReview;
} = {}) {
  const { account, authorizedFetch } = useAuth();
  const org = useOrganization();
  const { conversationId } = useParams();

  const reviewing = review !== undefined;
  const liveActive =
    org.status === "ready"
      ? (org.organizations.find((item) => item.id === org.activeId) ?? null)
      : null;
  const organization = reviewing ? REVIEW_WORKSPACE_ORGANIZATION : liveActive;

  const live = useProtocolOverview(
    reviewing ? null : (liveActive?.id ?? null),
    reviewing ? null : (conversationId ?? null),
    authorizedFetch,
  );
  const sample = reviewing ? reviewOverview(review) : null;
  const overview = sample ?? live;

  const accountId = reviewing
    ? REVIEW_WORKSPACE_ORGANIZATION.owner_account_id
    : (account?.id ?? null);
  const title = overview.conversation?.title ?? "Protocol workspace";

  return (
    <div className="protocol-workspace">
      <a className="protocol-workspace__skip" href="#protocol-workspace-main">
        Skip to main content
      </a>

      <WorkspaceChrome
        conversationId={conversationId ?? overview.conversation?.id ?? ""}
        protocolTitle={title}
        organization={organization}
        current="instructions"
        reviewing={reviewing}
      />

      <main id="protocol-workspace-main" className="protocol-workspace__main">
        <div className="protocol-workspace__page-header">
          <p className="protocol-workspace__page-eyebrow">
            Durable workspace context
          </p>
          <h1>Writing instructions</h1>
          <p className="protocol-workspace__lede">
            Instructions apply to every draft written in this protocol
            workspace.
          </p>
        </div>

        {overview.status === "loading" && (
          <section className="protocol-workspace__state" aria-label="Instructions">
            <LoadingState label="Loading this protocol workspace…" />
          </section>
        )}

        {overview.status === "error" && (
          <section className="protocol-workspace__state" aria-label="Instructions">
            <ErrorState
              message="Could not load this protocol workspace."
              onRetry={overview.retry}
            />
          </section>
        )}

        {overview.status === "ready" && (
          <div className="protocol-workspace__columns">
            <section
              className="protocol-workspace__primary"
              aria-labelledby="instruction-list-title"
            >
              <h2
                className="protocol-workspace__section-title"
                id="instruction-list-title"
              >
                Saved instructions
              </h2>

              {overview.feedback !== null && (
                <p
                  className={
                    overview.feedback.kind === "error"
                      ? "protocol-workspace__feedback protocol-workspace__feedback--error"
                      : "protocol-workspace__feedback"
                  }
                  role={overview.feedback.kind === "error" ? "alert" : "status"}
                >
                  {overview.feedback.message}
                </p>
              )}

              <InstructionTimeline
                instructions={overview.instructions}
                accountId={accountId}
              />

              <InstructionComposer
                pending={overview.action === "saving"}
                disabled={overview.conversation?.status === "archived"}
                onSave={overview.addInstruction}
              />

              {overview.conversation?.status === "archived" && (
                <p className="protocol-workspace__archived" role="status">
                  This protocol is archived. Restore it from the library to add
                  instructions.
                </p>
              )}
            </section>

            <GenerationPanel sourceCount={overview.documents.length} />
          </div>
        )}
      </main>
    </div>
  );
}
