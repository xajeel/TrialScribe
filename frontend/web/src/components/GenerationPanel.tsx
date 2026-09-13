import type { GenerationAttemptRecord, JobRecord } from "../api/types";
import { isJobInFlight } from "../workspace/useGenerationJob";

export function generationErrorText(code: string | null): string {
  if (code === "provider_failed") {
    return "The writing service did not finish.";
  }
  if (code === "empty_output") {
    return "The draft was empty.";
  }
  if (code === "missing_section") {
    return "That section was missing.";
  }
  if (code === "revision_conflict") {
    return "That section already changed.";
  }
  return "That section could not be written.";
}

/**
 * Live generation controls, or the review-only unavailable copy when
 * `reviewing` is set so fixture routes stay fetch-free.
 */
export function GenerationPanel({
  sourceCount,
  reviewing = false,
  job = null,
  attempts = [],
  emptyDraftCount = 0,
  pending = false,
  error = null,
  onGenerate,
  onCancel,
  onRetryFailed,
}: {
  sourceCount: number;
  reviewing?: boolean;
  job?: JobRecord | null;
  attempts?: GenerationAttemptRecord[];
  emptyDraftCount?: number;
  pending?: boolean;
  error?: string | null;
  onGenerate?: () => void;
  onCancel?: () => void;
  onRetryFailed?: () => void;
}) {
  const inFlight = isJobInFlight(job?.status);
  const failedCount = attempts.filter((item) => item.status === "failed").length;

  return (
    <aside
      className="generation-panel"
      aria-labelledby="generation-panel-title"
    >
      <h2 id="generation-panel-title">Generate section drafts</h2>
      {reviewing ? (
        <>
          <p className="generation-panel__status">
            Draft generation is not available yet. Sections are written and revised
            manually in the workspace.
          </p>
          <p className="generation-panel__note">
            Saved instructions will apply automatically once generation is
            available.
          </p>
        </>
      ) : (
        <>
          {inFlight && job !== null && (
            <div
              className="generation-panel__progress"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={job.progress}
              aria-label="Generation progress"
            >
              <span
                className="generation-panel__progress-bar"
                style={{ width: `${job.progress}%` }}
              />
            </div>
          )}
          {error !== null && (
            <p className="generation-panel__alert" role="alert">
              {error}
            </p>
          )}
          <div className="generation-panel__actions">
            {!inFlight && (
              <button
                type="button"
                className="generation-panel__primary"
                disabled={pending || emptyDraftCount === 0}
                onClick={onGenerate}
              >
                Generate
              </button>
            )}
            {inFlight && (
              <button
                type="button"
                className="generation-panel__secondary"
                disabled={pending}
                onClick={onCancel}
              >
                Cancel
              </button>
            )}
            {!inFlight && failedCount > 0 && (
              <button
                type="button"
                className="generation-panel__secondary"
                disabled={pending}
                onClick={onRetryFailed}
              >
                Retry failed sections
              </button>
            )}
          </div>
          {attempts.length > 0 && (
            <ul className="generation-panel__attempts" aria-label="Section generation">
              {attempts.map((item) => (
                <li key={`${item.section_number}-${item.attempt}`}>
                  <span>
                    Section {item.section_number} · {item.status}
                  </span>
                  {item.status === "failed" && (
                    <span className="generation-panel__attempt-error">
                      {generationErrorText(item.error_code)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <dl className="generation-panel__facts">
        <div>
          <dt>Saved sources</dt>
          <dd>
            {sourceCount === 0
              ? "None uploaded"
              : `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`}
          </dd>
        </div>
        <div>
          <dt>Drafting</dt>
          <dd>{reviewing ? "Manual" : inFlight ? "In progress" : "Ready"}</dd>
        </div>
      </dl>
    </aside>
  );
}
