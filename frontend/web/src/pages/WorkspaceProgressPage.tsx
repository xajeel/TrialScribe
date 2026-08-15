import { useParams } from "react-router-dom";

import type { DocumentRecord, GenerationAttemptRecord } from "../api/types";
import { ErrorState, LoadingState } from "../components/AsyncState";
import { generationErrorText } from "../components/GenerationPanel";
import {
  SectionProgressList,
  sectionStateOf,
} from "../components/SectionProgressList";
import { SourceProcessingList } from "../components/SourceProcessingList";
import { WorkspaceChrome } from "../components/WorkspaceChrome";
import { useAuth } from "../auth/useAuth";
import { useOrganization } from "../org/useOrganization";
import { isJobInFlight, useGenerationJob } from "../workspace/useGenerationJob";
import { useProtocolOverview } from "../workspace/useProtocolOverview";
import {
  REVIEW_WORKSPACE_ORGANIZATION,
  reviewProgress,
  type ProgressReview,
} from "../product/workspaceReviewFixtures";

const ATTENTION_LIMIT = 3;

interface AttentionItem {
  id: string;
  filename: string;
  reason: string;
  tone: "error" | "warning";
}

/** Attention rows from real document states, then generation failures. */
export function attentionFor(
  documents: DocumentRecord[],
  attempts: GenerationAttemptRecord[] = [],
): AttentionItem[] {
  const failed = documents
    .filter((record) => record.status === "failed")
    .map((record) => ({
      id: record.id,
      filename: record.filename,
      reason: "Processing failed. Re-upload this source to use it.",
      tone: "error" as const,
    }));
  const processing = documents
    .filter((record) => record.status === "pending")
    .map((record) => ({
      id: record.id,
      filename: record.filename,
      reason: "Still processing. It is not available to drafting yet.",
      tone: "warning" as const,
    }));
  const generation = attempts
    .filter((item) => item.status === "failed")
    .map((item) => ({
      id: `generation-${item.section_number}`,
      filename: `Section ${item.section_number}`,
      reason: generationErrorText(item.error_code),
      tone: "error" as const,
    }));
  return [...failed, ...generation, ...processing].slice(0, ATTENTION_LIMIT);
}

function ProgressRule({ done, total }: { done: number; total: number }) {
  const segments = Math.max(total, 1);
  return (
    <span className="protocol-progress" aria-hidden="true">
      {Array.from({ length: segments }, (_, index) => (
        <span
          key={index}
          className={
            index < done
              ? "protocol-progress__segment protocol-progress__segment--done"
              : "protocol-progress__segment"
          }
        />
      ))}
    </span>
  );
}

/** Real drafting state across the protocol's ICH M11 sections and sources. */
export function WorkspaceProgressPage({
  review,
}: {
  review?: ProgressReview;
} = {}) {
  const { authorizedFetch } = useAuth();
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
  const sample = reviewing ? reviewProgress(review) : null;
  const overview = sample ?? live;
  const generation = useGenerationJob({
    organizationId: reviewing ? null : (liveActive?.id ?? null),
    conversationId: reviewing ? null : (conversationId ?? null),
    sections: overview.sections,
    fetcher: authorizedFetch,
    enabled: !reviewing && overview.status === "ready",
    onTerminal: overview.retry,
  });
  const writing = isJobInFlight(generation.job?.status);

  const workspaceId = conversationId ?? overview.conversation?.id ?? "";
  const title = overview.conversation?.title ?? "Protocol workspace";

  const states = overview.sections.map(sectionStateOf);
  const done = states.filter((state) => state === "done").length;
  const drafted = states.filter((state) => state === "drafted").length;
  const notStarted = states.filter((state) => state === "empty").length;
  const total = overview.sections.length;
  const allDone = total > 0 && done === total;
  const attention = attentionFor(overview.documents, generation.attempts);

  return (
    <div className="protocol-workspace">
      <a className="protocol-workspace__skip" href="#protocol-workspace-main">
        Skip to main content
      </a>

      <WorkspaceChrome
        conversationId={workspaceId}
        protocolTitle={title}
        organization={organization}
        current="progress"
        reviewing={reviewing}
      />

      <main id="protocol-workspace-main" className="protocol-workspace__main">
        <div className="protocol-workspace__page-header">
          <p className="protocol-workspace__page-eyebrow">Drafting status</p>
          <h1>Protocol progress</h1>
          {overview.status === "ready" && overview.sectionsInitialized && (
            <p className="protocol-workspace__lede">
              {done} done · {drafted} drafted · {notStarted} not started, of{" "}
              {total} sections.
              {writing && generation.job !== null
                ? ` Writing… ${generation.job.progress}%.`
                : ""}
            </p>
          )}
        </div>

        {overview.status === "loading" && (
          <section className="protocol-workspace__state" aria-label="Progress">
            <LoadingState label="Loading this protocol workspace…" />
          </section>
        )}

        {overview.status === "error" && (
          <section className="protocol-workspace__state" aria-label="Progress">
            <ErrorState
              message="Could not load this protocol workspace."
              onRetry={overview.retry}
            />
          </section>
        )}

        {overview.status === "ready" && !overview.sectionsInitialized && (
          <section
            className="protocol-workspace__not-started"
            aria-labelledby="progress-not-started-title"
          >
            <h2 id="progress-not-started-title">Sections not started</h2>
            <p>
              Open the workspace to prepare the 14-section ICH M11 outline.
            </p>
          </section>
        )}

        {overview.status === "ready" && overview.sectionsInitialized && (
          <>
            {attention.length > 0 && (
              <section
                className="progress-attention"
                aria-labelledby="progress-attention-title"
              >
                <h2 id="progress-attention-title">Needs attention</h2>
                <ul>
                  {attention.map((item) => (
                    <li
                      key={item.id}
                      className={`progress-attention__item progress-attention__item--${item.tone}`}
                    >
                      <span className="progress-attention__name">
                        {item.filename}
                      </span>
                      <span className="progress-attention__reason">
                        {item.reason}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section
              className={
                allDone
                  ? "progress-summary progress-summary--complete"
                  : "progress-summary"
              }
              aria-labelledby="progress-summary-title"
            >
              <h2 id="progress-summary-title">
                {allDone ? "All sections drafted" : "Section completion"}
              </h2>
              <p className="progress-summary__count">
                {done} of {total} sections complete
              </p>
              <ProgressRule done={done} total={total} />
              {allDone && (
                <p className="progress-summary__note">
                  Every section has been marked done. Review the protocol
                  before export.
                </p>
              )}
            </section>

            <section
              className="protocol-workspace__panel"
              aria-labelledby="progress-sections-title"
            >
              <h2
                className="protocol-workspace__section-title"
                id="progress-sections-title"
              >
                Sections
              </h2>
              <SectionProgressList
                sections={overview.sections}
                conversationId={workspaceId}
                attempts={generation.attempts}
                onRetrySection={
                  reviewing
                    ? undefined
                    : (sectionNumber) => {
                        void generation.retryFailed(sectionNumber);
                      }
                }
              />
            </section>

            <section
              className="protocol-workspace__panel"
              aria-labelledby="progress-sources-title"
            >
              <h2
                className="protocol-workspace__section-title"
                id="progress-sources-title"
              >
                Sources
              </h2>
              <SourceProcessingList
                documents={overview.documents}
                conversationId={workspaceId}
              />
            </section>
          </>
        )}
      </main>
    </div>
  );
}
