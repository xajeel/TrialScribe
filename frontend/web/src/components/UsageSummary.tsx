import {
  formatCostMicros,
  type UsageView,
} from "../product/deliveryAuditReviewFixtures";

function formatUpdated(value: string | null): string {
  if (value === null) return "No finalized activity";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}
export function UsageSummary({ view }: { view: UsageView }) {
  const { summary } = view;
  return (
    <>
      <section className="usage-total" aria-labelledby="usage-total-title">
        <div>
          <p id="usage-total-title">Protocol workspace total</p>
          <strong>{formatCostMicros(summary.totalCostMicros)}</strong>
        </div>
        <p>
          <strong>{summary.generationCount} generations</strong>
          <span>Updated {formatUpdated(summary.updatedAt)}</span>
        </p>
      </section>
      <section className="usage-summary" aria-labelledby="usage-summary-title">
        <h2 id="usage-summary-title">Metadata summary</h2>
        <dl>
          <div>
            <dt>Input tokens</dt>
            <dd>{summary.inputTokens.toLocaleString()}</dd>
          </div>
          <div>
            <dt>Output tokens</dt>
            <dd>{summary.outputTokens.toLocaleString()}</dd>
          </div>
          <div>
            <dt>Successful jobs</dt>
            <dd>{summary.successfulJobs}</dd>
          </div>
          <div>
            <dt>Failed or cancelled</dt>
            <dd>{summary.failedOrCancelled}</dd>
          </div>
          <div className="usage-summary__pricing">
            <dt>Pricing basis</dt>
            <dd>{summary.pricingBasis}</dd>
          </div>
        </dl>
        <p>
          Totals are calculated from recorded provider calls and persist with
          this workspace.
        </p>
      </section>
    </>
  );
}
