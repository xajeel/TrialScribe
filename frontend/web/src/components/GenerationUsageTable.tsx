import { Fragment, useMemo, useState } from "react";

import {
  formatCostMicros,
  type GenerationUsageView,
  type UsageOutcome,
  type UsageView,
} from "../product/deliveryAuditReviewFixtures";

export type UsageOutcomeFilter = "all" | "complete" | "attention" | "running";
export type UsageSort = "newest" | "oldest";
export type UsageDateRange = "all" | "24-hours" | "7-days" | "30-days";

export interface UsageFiltersValue {
  dateRange: UsageDateRange;
  section: string;
  outcome: UsageOutcomeFilter;
  sort: UsageSort;
}

export const DEFAULT_USAGE_FILTERS: UsageFiltersValue = {
  dateRange: "all",
  section: "all",
  outcome: "all",
  sort: "newest",
};

function outcomeLabel(outcome: UsageOutcome): string {
  const labels: Record<UsageOutcome, string> = {
    complete: "Complete",
    issue: "Completed with issue",
    failed: "Failed",
    cancelled: "Cancelled",
    running: "In progress",
  };
  return labels[outcome];
}

function formatDate(value: string): string {
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

function formatLatency(value: number | null): string {
  if (value === null) return "Finalizes on completion";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`;
}

function totalTokens(record: GenerationUsageView): string {
  const value = record.inputTokens + record.outputTokens;
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k`;
  }
  return value.toLocaleString();
}

function ProviderCallTable({ record }: { record: GenerationUsageView }) {
  if (record.providerCalls.length === 0) {
    return (
      <p className="usage-detail__empty">
        No provider-call breakdown is available for this review record.
      </p>
    );
  }
  return (
    <div className="provider-call-wrap">
      <table className="provider-call-table">
        <caption>Provider-call breakdown</caption>
        <thead>
          <tr>
            <th>Stage</th>
            <th>Model</th>
            <th>Input</th>
            <th>Output</th>
            <th>Latency</th>
            <th>Result</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {record.providerCalls.map((call) => (
            <tr key={call.id}>
              <th scope="row">{call.stage}</th>
              <td>{call.model}</td>
              <td>{call.inputTokens.toLocaleString()}</td>
              <td>{call.outputTokens.toLocaleString()}</td>
              <td>{formatLatency(call.latencyMs)}</td>
              <td>{call.result}</td>
              <td>
                {call.costMicros === null
                  ? "Finalizes on completion"
                  : formatCostMicros(call.costMicros)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UsageDetail({
  record,
  onClose,
}: {
  record: GenerationUsageView;
  onClose: () => void;
}) {
  return (
    <div className="usage-detail" id={`usage-detail-${record.id}`}>
      <div className="usage-detail__heading">
        <div>
          <p>Generation audit</p>
          <h3>{record.jobId}</h3>
        </div>
        <button type="button" onClick={onClose}>
          Close detail
        </button>
      </div>
      <dl>
        <div><dt>Requested sections</dt><dd>{record.scope}</dd></div>
        <div><dt>Provider / model</dt><dd>{record.model}</dd></div>
        <div><dt>Input tokens</dt><dd>{record.inputTokens.toLocaleString()}</dd></div>
        <div><dt>Output tokens</dt><dd>{record.outputTokens.toLocaleString()}</dd></div>
        <div><dt>Recorded latency</dt><dd>{formatLatency(record.latencyMs)}</dd></div>
        <div><dt>Outcome</dt><dd>{outcomeLabel(record.outcome)}</dd></div>
        <div>
          <dt>Exact cost</dt>
          <dd>{record.costMicros === null ? "Finalizes on completion" : formatCostMicros(record.costMicros)}</dd>
        </div>
        <div><dt>Pricing version</dt><dd>{record.pricingVersion}</dd></div>
        <div><dt>Started</dt><dd>{formatDate(record.startedAt)}</dd></div>
        <div><dt>Completed</dt><dd>{record.completedAt === null ? "In progress" : formatDate(record.completedAt)}</dd></div>
      </dl>
      <ProviderCallTable record={record} />
    </div>
  );
}

function matchesOutcome(
  outcome: UsageOutcome,
  filter: UsageOutcomeFilter,
): boolean {
  if (filter === "all") return true;
  if (filter === "complete") return outcome === "complete";
  if (filter === "running") return outcome === "running";
  return outcome === "issue" || outcome === "failed" || outcome === "cancelled";
}

function matchesDateRange(
  startedAt: string,
  range: UsageDateRange,
  now: number,
): boolean {
  if (range === "all") return true;
  const started = new Date(startedAt).getTime();
  if (Number.isNaN(started)) return false;
  const days = range === "24-hours" ? 1 : range === "7-days" ? 7 : 30;
  return started <= now && started >= now - days * 24 * 60 * 60 * 1000;
}

export function GenerationUsageTable({
  view,
  filters,
  onFiltersChange,
  initialExpandedId,
  error = false,
  onRetry,
}: {
  view: UsageView;
  filters: UsageFiltersValue;
  onFiltersChange: (filters: UsageFiltersValue) => void;
  initialExpandedId?: string;
  error?: boolean;
  onRetry?: () => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(
    initialExpandedId ?? null,
  );
  const [opener, setOpener] = useState<HTMLButtonElement | null>(null);
  const sectionOptions = useMemo(
    () =>
      [...new Set(view.generations.flatMap((record) => record.sectionNumbers))].sort(
        (left, right) => Number(left) - Number(right),
      ),
    [view.generations],
  );
  const visible = useMemo(() => {
    const now = Date.now();
    const records = view.generations.filter(
      (record) =>
        matchesDateRange(record.startedAt, filters.dateRange, now) &&
        (filters.section === "all" ||
          record.sectionNumbers.includes(filters.section)) &&
        matchesOutcome(record.outcome, filters.outcome),
    );
    return [...records].sort((left, right) =>
      filters.sort === "newest"
        ? right.startedAt.localeCompare(left.startedAt)
        : left.startedAt.localeCompare(right.startedAt),
    );
  }, [filters, view.generations]);

  const closeDetail = () => {
    setExpandedId(null);
    queueMicrotask(() => opener?.focus());
  };

  return (
    <section className="usage-history" aria-labelledby="usage-history-title">
      <div className="usage-history__heading">
        <h2 id="usage-history-title">Generation history</h2>
        <div className="usage-filters" aria-label="Usage filters">
          <label>
            <span>Date range</span>
            <select
              value={filters.dateRange}
              onChange={(event) =>
                onFiltersChange({
                  ...filters,
                  dateRange: event.target.value as UsageDateRange,
                })
              }
            >
              <option value="all">All time</option>
              <option value="24-hours">Last 24 hours</option>
              <option value="7-days">Last 7 days</option>
              <option value="30-days">Last 30 days</option>
            </select>
          </label>
          <label>
            <span>Section</span>
            <select
              value={filters.section}
              onChange={(event) =>
                onFiltersChange({ ...filters, section: event.target.value })
              }
            >
              <option value="all">All sections</option>
              {sectionOptions.map((section) => (
                <option key={section} value={section}>Section {section}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Outcome</span>
            <select
              value={filters.outcome}
              onChange={(event) =>
                onFiltersChange({
                  ...filters,
                  outcome: event.target.value as UsageOutcomeFilter,
                })
              }
            >
              <option value="all">All outcomes</option>
              <option value="complete">Complete</option>
              <option value="attention">Needs attention</option>
              <option value="running">In progress</option>
            </select>
          </label>
          <label>
            <span>Order</span>
            <select
              value={filters.sort}
              onChange={(event) =>
                onFiltersChange({
                  ...filters,
                  sort: event.target.value as UsageSort,
                })
              }
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </label>
        </div>
      </div>

      {error ? (
        <div className="usage-history__state usage-history__state--error" role="alert">
          <span aria-hidden="true">!</span>
          <h3>Could not load usage.</h3>
          {onRetry !== undefined && <button type="button" onClick={onRetry}>Try again</button>}
        </div>
      ) : view.generations.length === 0 ? (
        <div className="usage-history__state" role="status">
          <span aria-hidden="true">◷</span>
          <h3>No model usage recorded for this workspace.</h3>
          <p>Usage appears after a generation job completes.</p>
        </div>
      ) : visible.length === 0 ? (
        <div className="usage-history__state" role="status">
          <h3>No generations match these filters.</h3>
          <button
            type="button"
            onClick={() => onFiltersChange(DEFAULT_USAGE_FILTERS)}
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="usage-table-wrap">
          <table className="usage-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Scope</th>
                <th>Requested by</th>
                <th>Model</th>
                <th>Tokens</th>
                <th>Outcome</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((record) => {
                const expanded = expandedId === record.id;
                return (
                  <Fragment key={record.id}>
                    <tr key={record.id} className={`usage-row usage-row--${record.outcome}`}>
                      <td data-label="Time">{formatDate(record.startedAt)}</td>
                      <th scope="row" data-label="Scope">
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-controls={`usage-detail-${record.id}`}
                          onClick={(event) => {
                            setOpener(event.currentTarget);
                            setExpandedId(expanded ? null : record.id);
                          }}
                        >
                          {record.scope}
                        </button>
                      </th>
                      <td data-label="Requested by">{record.requester}</td>
                      <td data-label="Model">{record.model}</td>
                      <td data-label="Tokens">{record.outcome === "running" ? "Finalizes on completion" : totalTokens(record)}</td>
                      <td data-label="Outcome"><span className={`usage-outcome usage-outcome--${record.outcome}`}>{outcomeLabel(record.outcome)}</span></td>
                      <td data-label="Cost">{record.costMicros === null ? "Finalizes on completion" : formatCostMicros(record.costMicros)}</td>
                    </tr>
                    {expanded && (
                      <tr key={`${record.id}-detail`} className="usage-row-detail">
                        <td colSpan={7}>
                          <UsageDetail record={record} onClose={closeDetail} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
