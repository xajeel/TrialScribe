import type { ReadinessView } from "../product/governanceReviewFixtures";

function formatActivity(value: string | null): string {
  if (value === null) return "No activity yet";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/** Compact Page 15 fact band; citation facts render only when supplied. */
export function ReadinessSummary({ data }: { data: ReadinessView }) {
  const { summary } = data;
  return (
    <section className="readiness-summary" aria-labelledby="readiness-summary-title">
      <h2 id="readiness-summary-title" className="visually-hidden">Readiness summary</h2>
      <dl>
        <div>
          <dt><span aria-hidden="true">§</span> Sections</dt>
          <dd><strong>{summary.doneSections}</strong> done · {summary.draftSections} draft</dd>
        </div>
        {summary.citations !== undefined && (
          <div>
            <dt><span aria-hidden="true">⌁</span> Citations</dt>
            <dd>
              <strong>{summary.citations.resolved}</strong> resolved
              {summary.citations.needingReview > 0 && ` · ${summary.citations.needingReview} needs review`}
            </dd>
          </div>
        )}
        <div>
          <dt><span aria-hidden="true">▤</span> Sources</dt>
          <dd>
            <strong>{summary.readySources}</strong> ready
            {summary.pendingSources > 0 && ` · ${summary.pendingSources} pending`}
            {summary.failedSources > 0 && ` · ${summary.failedSources} failed`}
          </dd>
        </div>
        <div>
          <dt><span aria-hidden="true">◷</span> Latest activity</dt>
          <dd>{formatActivity(summary.latestActivity)}</dd>
        </div>
      </dl>
      {data.ready && (
        <div className="readiness-summary__complete" role="status">
          <strong>Protocol checks complete</strong>
          <span>All loaded sections are Done and every known source is ready.</span>
        </div>
      )}
      {!data.ready && (
        <p className="readiness-summary__incomplete">
          Review unfinished sections and known source issues before preparing an export.
        </p>
      )}
      {data.fixtureNote !== undefined && <p className="readiness-summary__fixture">{data.fixtureNote}</p>}
    </section>
  );
}
