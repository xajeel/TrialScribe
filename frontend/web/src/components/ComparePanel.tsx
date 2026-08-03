import type {
  DiffSegment,
  RewriteAlternative,
  RewriteReviewFixture,
} from "../product/evidenceRewriteReviewFixtures";

export type CompareView = "side-by-side" | "inline";

export interface ComparePanelProps {
  fixture: RewriteReviewFixture;
  alternative: RewriteAlternative;
  view: CompareView;
  onChangeView: (view: CompareView) => void;
  onBack: () => void;
  onUse: (opener: HTMLElement) => void;
}

function DiffText({ segments }: { segments: ReadonlyArray<DiffSegment> }) {
  return (
    <p className="compare-panel__text">
      {segments.map((segment, index) => {
        const key = `${segment.kind}-${index}`;
        if (segment.kind === "removed") {
          return <del key={key}>{segment.text}</del>;
        }
        if (segment.kind === "added") {
          return <ins key={key}>{segment.text}</ins>;
        }
        return <span key={key}>{segment.text}</span>;
      })}
    </p>
  );
}

/** Semantic Page 13 comparison over deterministic, fixture-owned segments. */
export function ComparePanel({
  fixture,
  alternative,
  view,
  onChangeView,
  onBack,
  onUse,
}: ComparePanelProps) {
  const laterSegments =
    alternative.id === "alternative-1"
      ? fixture.currentSegments
      : alternative.segments;

  return (
    <section className="compare-panel" aria-labelledby="compare-panel-title">
      <header className="compare-panel__header">
        <div>
          <p className="compare-panel__eyebrow">
            Section {fixture.sectionNumber} · {fixture.sectionTitle}
          </p>
          <h1 id="compare-panel-title">Compare wording</h1>
        </div>
        <button type="button" className="compare-panel__back" onClick={onBack}>
          Back to alternatives
        </button>
      </header>

      <div className="compare-panel__toolbar">
        <div className="compare-panel__revisions" aria-label="Compared revisions">
          <span>
            Earlier <strong>Revision {fixture.currentRevision}</strong>
          </span>
          <span aria-hidden="true">→</span>
          <span>
            Later <strong>Review alternative</strong>
          </span>
        </div>
        <div className="compare-panel__counts" aria-label="Change summary">
          <span className="compare-panel__count compare-panel__count--added">
            {fixture.additions} additions
          </span>
          <span className="compare-panel__count compare-panel__count--removed">
            {fixture.removals} removals
          </span>
        </div>
        <div className="compare-panel__views" aria-label="Comparison view">
          <button
            type="button"
            aria-pressed={view === "side-by-side"}
            onClick={() => onChangeView("side-by-side")}
          >
            Side by side
          </button>
          <button
            type="button"
            aria-pressed={view === "inline"}
            onClick={() => onChangeView("inline")}
          >
            Inline
          </button>
        </div>
      </div>

      {view === "side-by-side" ? (
        <div className="compare-panel__documents compare-panel__documents--side">
          <article aria-labelledby="compare-earlier-title">
            <p className="compare-panel__document-label">Revision {fixture.currentRevision} · Earlier</p>
            <h2 id="compare-earlier-title">{fixture.sectionTitle}</h2>
            <DiffText segments={fixture.oldSegments} />
          </article>
          <article aria-labelledby="compare-later-title">
            <p className="compare-panel__document-label">{alternative.label} · Later</p>
            <h2 id="compare-later-title">{fixture.sectionTitle}</h2>
            <DiffText segments={laterSegments} />
          </article>
        </div>
      ) : (
        <article
          className="compare-panel__documents compare-panel__documents--inline"
          aria-labelledby="compare-inline-title"
        >
          <p className="compare-panel__document-label">Inline changes</p>
          <h2 id="compare-inline-title">{fixture.sectionTitle}</h2>
          <div className="compare-panel__inline-change">
            <DiffText segments={fixture.oldSegments} />
            <span className="compare-panel__inline-divider" aria-hidden="true">
              Revised wording
            </span>
            <DiffText segments={laterSegments} />
          </div>
        </article>
      )}

      <footer className="compare-panel__footer">
        <p>
          Review fixture — choosing this wording opens confirmation and does
          not change stored content.
        </p>
        <button
          type="button"
          className="compare-panel__use"
          onClick={(event) => onUse(event.currentTarget)}
        >
          Use this version
        </button>
      </footer>
    </section>
  );
}
