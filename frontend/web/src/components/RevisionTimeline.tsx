import { useMemo, useState } from "react";

import type {
  RevisionDisplayAction,
  RevisionRowView,
} from "../product/governanceReviewFixtures";

export type RevisionTimelineStatus = "loading" | "ready" | "error";
export type RevisionDateFilter = "all" | "7-days" | "30-days";

export interface RevisionFiltersValue {
  author: string;
  action: "all" | RevisionDisplayAction;
  date: RevisionDateFilter;
}

export const EMPTY_REVISION_FILTERS: RevisionFiltersValue = {
  author: "all",
  action: "all",
  date: "all",
};

export interface RevisionTimelineProps {
  status: RevisionTimelineStatus;
  rows: ReadonlyArray<RevisionRowView>;
  filters: RevisionFiltersValue;
  onFiltersChange: (filters: RevisionFiltersValue) => void;
  onPreview: (revision: RevisionRowView, opener: HTMLElement) => void;
  onCompare?: (revision: RevisionRowView) => void;
  onRetry: () => void;
  onReturnToDocument: () => void;
}

function actionGlyph(action: RevisionDisplayAction): string {
  if (action === "edited") return "✎";
  if (action === "generated") return "▤";
  if (action === "marked-done") return "✓";
  if (action === "reopened") return "↗";
  return "↶";
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function RevisionFilters({
  value,
  authors,
  onChange,
}: {
  value: RevisionFiltersValue;
  authors: ReadonlyArray<string>;
  onChange: (filters: RevisionFiltersValue) => void;
}) {
  return (
    <div className="revision-filters" aria-label="Revision filters">
      <label>
        <span>Author</span>
        <select
          value={value.author}
          onChange={(event) => onChange({ ...value, author: event.target.value })}
        >
          <option value="all">All authors</option>
          {authors.map((author) => (
            <option key={author} value={author}>
              {author}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Action</span>
        <select
          value={value.action}
          onChange={(event) =>
            onChange({
              ...value,
              action: event.target.value as RevisionFiltersValue["action"],
            })
          }
        >
          <option value="all">All actions</option>
          <option value="edited">Edited</option>
          <option value="generated">Generated draft</option>
          <option value="marked-done">Marked done</option>
          <option value="reopened">Reopened</option>
          <option value="restored">Restored</option>
        </select>
      </label>
      <label>
        <span>Date</span>
        <select
          value={value.date}
          onChange={(event) =>
            onChange({
              ...value,
              date: event.target.value as RevisionDateFilter,
            })
          }
        >
          <option value="all">All dates</option>
          <option value="7-days">Last 7 days</option>
          <option value="30-days">Last 30 days</option>
        </select>
      </label>
      <button
        type="button"
        className="revision-filters__reset"
        disabled={
          value.author === "all" && value.action === "all" && value.date === "all"
        }
        onClick={() => onChange(EMPTY_REVISION_FILTERS)}
      >
        Reset filters
      </button>
    </div>
  );
}

function RevisionRow({
  revision,
  expanded,
  onToggle,
  onPreview,
  onCompare,
}: {
  revision: RevisionRowView;
  expanded: boolean;
  onToggle: () => void;
  onPreview: (opener: HTMLElement) => void;
  onCompare?: () => void;
}) {
  const detailsId = `revision-${revision.id}-details`;
  return (
    <li className={revision.current ? "revision-row revision-row--current" : "revision-row"}>
      <span className="revision-row__node" aria-hidden="true" />
      <div className="revision-row__icon" aria-hidden="true">
        {actionGlyph(revision.action)}
      </div>
      <div className="revision-row__body">
        <button
          type="button"
          className="revision-row__toggle"
          aria-expanded={expanded}
          aria-controls={detailsId}
          onClick={onToggle}
        >
          <span className="revision-row__identity">
            <strong>Revision {revision.revisionNumber}</strong>
            <span>{revision.actionLabel}</span>
            {revision.current && <em>Current</em>}
          </span>
          <span className="revision-row__byline">
            {revision.authorLabel} · {formatDate(revision.createdAt)}
          </span>
        </button>
        <div
          id={detailsId}
          className={
            expanded
              ? "revision-row__details revision-row__details--expanded"
              : "revision-row__details"
          }
        >
          <p>{revision.summary}</p>
          <div className="revision-row__facts">
            {revision.wordDelta !== undefined ? (
              <span>{revision.wordDelta}</span>
            ) : (
              <span>{revision.words.toLocaleString()} words</span>
            )}
            {revision.sourceSummary !== undefined && (
              <span>{revision.sourceSummary}</span>
            )}
            {revision.citationSummary !== undefined && (
              <span>{revision.citationSummary}</span>
            )}
            <span>Status at revision: {revision.status === "done" ? "Done" : "Draft"}</span>
          </div>
          <div className="revision-row__actions">
            <button type="button" onClick={(event) => onPreview(event.currentTarget)}>
              Preview
            </button>
            {onCompare !== undefined && (
              <button type="button" onClick={onCompare}>
                Compare
              </button>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

/** Immutable, newest-first Page 14 history with one adaptive row model. */
export function RevisionTimeline({
  status,
  rows,
  filters,
  onFiltersChange,
  onPreview,
  onCompare,
  onRetry,
  onReturnToDocument,
}: RevisionTimelineProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const authors = useMemo(
    () => [...new Set(rows.map((row) => row.authorLabel))].sort(),
    [rows],
  );
  const latestTime = Math.max(
    ...rows.map((row) => new Date(row.createdAt).getTime()).filter(Number.isFinite),
    0,
  );
  const visible = rows.filter((row) => {
    if (filters.author !== "all" && row.authorLabel !== filters.author) {
      return false;
    }
    if (filters.action !== "all" && row.action !== filters.action) {
      return false;
    }
    if (filters.date !== "all") {
      const days = filters.date === "7-days" ? 7 : 30;
      const rowTime = new Date(row.createdAt).getTime();
      if (!Number.isFinite(rowTime) || rowTime < latestTime - days * 86_400_000) {
        return false;
      }
    }
    return true;
  });

  if (status === "loading") {
    return (
      <section className="revision-timeline revision-timeline--loading" aria-label="Revision history">
        <p role="status">Loading revision history…</p>
        {[1, 2, 3, 4].map((row) => (
          <div key={row} className="revision-timeline__skeleton" aria-hidden="true" />
        ))}
      </section>
    );
  }

  if (status === "error") {
    return (
      <section className="revision-timeline revision-timeline__state" aria-label="Revision history">
        <div role="alert">
          <h2>Could not load revision history.</h2>
          <p>The document and protocol navigation are still available.</p>
        </div>
        <button type="button" onClick={onRetry}>Try again</button>
      </section>
    );
  }

  if (rows.length === 0) {
    return (
      <section className="revision-timeline revision-timeline__state" aria-labelledby="revision-empty-title">
        <h2 id="revision-empty-title">No revision history yet</h2>
        <p>The first saved edit or status change will create revision 1.</p>
        <button type="button" onClick={onReturnToDocument}>Return to document</button>
      </section>
    );
  }

  return (
    <section className="revision-timeline" aria-labelledby="revision-timeline-title">
      <h2 id="revision-timeline-title" className="visually-hidden">Revision timeline</h2>
      <RevisionFilters value={filters} authors={authors} onChange={onFiltersChange} />
      {visible.length === 0 ? (
        <div className="revision-timeline__no-match" role="status">
          <p>No revisions match these filters.</p>
          <button type="button" onClick={() => onFiltersChange(EMPTY_REVISION_FILTERS)}>
            Clear filters
          </button>
        </div>
      ) : (
        <ol className="revision-timeline__list">
          {visible.map((revision) => (
            <RevisionRow
              key={revision.id}
              revision={revision}
              expanded={expanded.has(revision.id)}
              onToggle={() =>
                setExpanded((current) => {
                  const next = new Set(current);
                  if (next.has(revision.id)) next.delete(revision.id);
                  else next.add(revision.id);
                  return next;
                })
              }
              onPreview={(opener) => onPreview(revision, opener)}
              onCompare={
                onCompare === undefined ? undefined : () => onCompare(revision)
              }
            />
          ))}
        </ol>
      )}
    </section>
  );
}
