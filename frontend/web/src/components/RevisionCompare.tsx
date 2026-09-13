import type {
  GovernanceDiffSegment,
  RevisionComparisonView,
} from "../product/governanceReviewFixtures";

export type RevisionCompareMode = "side-by-side" | "inline";

export function defaultRevisionCompareMode(): RevisionCompareMode {
  return typeof window !== "undefined" &&
    window.matchMedia?.("(max-width: 47.9375rem)").matches
    ? "inline"
    : "side-by-side";
}

function DiffSegments({
  segments,
}: {
  segments: ReadonlyArray<GovernanceDiffSegment>;
}) {
  return (
    <p className="revision-compare__text">
      {segments.map((segment, index) => {
        const key = `${segment.kind}-${index}`;
        if (segment.kind === "removed") {
          return (
            <del key={key} aria-label={`Removed: ${segment.text}`}>
              {segment.text}
            </del>
          );
        }
        if (segment.kind === "added") {
          return (
            <ins key={key} aria-label={`Added: ${segment.text}`}>
              {segment.text}
            </ins>
          );
        }
        return <span key={key}>{segment.text}</span>;
      })}
    </p>
  );
}

function RevisionIdentity({
  label,
  revision,
}: {
  label: "Earlier" | "Later";
  revision: RevisionComparisonView["earlier"];
}) {
  return (
    <div className="revision-compare__identity">
      <span>{label}</span>
      <strong>Revision {revision.revisionNumber}</strong>
      <small>
        {revision.actionLabel} · {revision.authorLabel}
      </small>
    </div>
  );
}

/** Page 14 comparison for real snapshots or pre-labelled review segments. */
export function RevisionCompare({
  comparison,
  mode,
  onModeChange,
  onBack,
  onKeepCurrent,
  onRestore,
}: {
  comparison: RevisionComparisonView;
  mode: RevisionCompareMode;
  onModeChange: (mode: RevisionCompareMode) => void;
  onBack: () => void;
  onKeepCurrent: () => void;
  onRestore?: (opener: HTMLElement) => void;
}) {
  const semantic =
    comparison.earlierSegments !== undefined &&
    comparison.laterSegments !== undefined;
  const hasCounts =
    comparison.additions !== undefined ||
    comparison.removals !== undefined ||
    comparison.citationChanges !== undefined;

  return (
    <section className="revision-compare" aria-labelledby="revision-compare-title">
      <header className="revision-compare__header">
        <div>
          <p>Compare revisions</p>
          <h1 id="revision-compare-title">5 · Trial Population</h1>
        </div>
        <button type="button" onClick={onBack}>Revision history</button>
      </header>

      <div className="revision-compare__toolbar">
        <RevisionIdentity label="Earlier" revision={comparison.earlier} />
        <span className="revision-compare__arrow" aria-hidden="true">→</span>
        <RevisionIdentity label="Later" revision={comparison.later} />
        <div className="revision-compare__modes" aria-label="Comparison view">
          <button
            type="button"
            aria-pressed={mode === "side-by-side"}
            onClick={() => onModeChange("side-by-side")}
          >
            Side by side
          </button>
          <button
            type="button"
            aria-pressed={mode === "inline"}
            onClick={() => onModeChange("inline")}
          >
            Inline
          </button>
        </div>
      </div>

      <div className="revision-compare__summary" role="status">
        {hasCounts ? (
          <>
            {comparison.additions !== undefined && <span>{comparison.additions} additions</span>}
            {comparison.removals !== undefined && <span>{comparison.removals} removals</span>}
            {comparison.citationChanges !== undefined && (
              <span>{comparison.citationChanges} citation change</span>
            )}
          </>
        ) : (
          <span>Complete stored snapshots shown. No semantic change counts are available.</span>
        )}
      </div>

      {mode === "side-by-side" ? (
        <div className="revision-compare__documents revision-compare__documents--side">
          <article aria-labelledby="revision-earlier-title">
            <p>Revision {comparison.earlier.revisionNumber} · Earlier</p>
            <h2 id="revision-earlier-title">Trial Population</h2>
            {semantic ? (
              <DiffSegments segments={comparison.earlierSegments ?? []} />
            ) : (
              <p className="revision-compare__text">{comparison.earlier.content}</p>
            )}
          </article>
          <article aria-labelledby="revision-later-title">
            <p>Revision {comparison.later.revisionNumber} · Later</p>
            <h2 id="revision-later-title">Trial Population</h2>
            {semantic ? (
              <DiffSegments segments={comparison.laterSegments ?? []} />
            ) : (
              <p className="revision-compare__text">{comparison.later.content}</p>
            )}
          </article>
        </div>
      ) : (
        <article className="revision-compare__documents revision-compare__documents--inline" aria-labelledby="revision-inline-title">
          <p>Inline changes</p>
          <h2 id="revision-inline-title">Trial Population</h2>
          {semantic ? (
            <>
              <DiffSegments segments={comparison.earlierSegments ?? []} />
              <span className="revision-compare__divider">Later wording</span>
              <DiffSegments segments={comparison.laterSegments ?? []} />
            </>
          ) : (
            <>
              <p className="revision-compare__text">{comparison.earlier.content}</p>
              <span className="revision-compare__divider">Later snapshot</span>
              <p className="revision-compare__text">{comparison.later.content}</p>
            </>
          )}
        </article>
      )}

      <footer className="revision-compare__footer">
        <p>Comparing stored snapshots does not change revision history.</p>
        <div>
          {onRestore !== undefined && (
            <button
              type="button"
              className="revision-compare__restore"
              onClick={(event) => onRestore(event.currentTarget)}
            >
              Restore revision {comparison.earlier.revisionNumber}
            </button>
          )}
          <button type="button" className="revision-compare__keep" onClick={onKeepCurrent}>
            Keep current
          </button>
        </div>
      </footer>
    </section>
  );
}
