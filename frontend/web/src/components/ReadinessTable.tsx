import { useEffect, useRef, useState } from "react";

import type {
  ReadinessIssueView,
  ReadinessSectionView,
  ReadinessView,
} from "../product/governanceReviewFixtures";

export type ReadinessFilter = "all" | "draft" | "done" | "attention";

function formatUpdated(value: string): string {
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

function IssueList({
  issues,
  onAction,
  checking,
}: {
  issues: ReadonlyArray<ReadinessIssueView>;
  onAction?: (issue: ReadinessIssueView) => void;
  checking?: boolean;
}) {
  if (issues.length === 0) return null;
  return (
    <section className="readiness-issues" aria-labelledby="readiness-issues-title">
      <h2 id="readiness-issues-title">Needs attention</h2>
      <ul>
        {issues.map((issue) => (
          <li key={issue.id} className={`readiness-issue readiness-issue--${issue.severity}`}>
            <span className="readiness-issue__icon" aria-hidden="true">
              {issue.severity === "error" ? "!" : "△"}
            </span>
            <div>
              <strong>{issue.title}</strong>
              <span>{issue.detail}</span>
            {issue.state === "retrying" && (
              <em role="status">Retrying in this review demonstration…</em>
            )}
            {checking === true && issue.action === "retry-check" && (
              <em role="status">Checking…</em>
            )}
              {issue.state === "resolved" && <em role="status">Resolved in this review demonstration.</em>}
            </div>
            {issue.actionLabel !== undefined && onAction !== undefined && (
              <button
                type="button"
                onClick={() => onAction(issue)}
                disabled={
                  issue.state === "retrying" ||
                  (checking === true && issue.action === "retry-check")
                }
              >
                {issue.actionLabel}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function QuickReview({
  section,
  returnFocusTo,
  onClose,
  onOpenSection,
  onOpenEditor,
  onViewHistory,
}: {
  section: ReadinessSectionView;
  returnFocusTo: HTMLElement | null;
  onClose: () => void;
  onOpenSection?: (section: ReadinessSectionView) => void;
  onOpenEditor?: (section: ReadinessSectionView) => void;
  onViewHistory?: (section: ReadinessSectionView) => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    return () => returnFocusTo?.focus();
  }, [returnFocusTo]);
  return (
    <aside className="readiness-quick" aria-labelledby="readiness-quick-title">
      <header>
        <div>
          <p>Reviewing section {section.sectionNumber}</p>
          <h2 id="readiness-quick-title">{section.title}</h2>
        </div>
        <button ref={closeRef} type="button" onClick={onClose} aria-label="Close section quick review">×</button>
      </header>
      <dl>
        <div><dt>Status</dt><dd>{section.status === "done" ? "Done" : "Draft"}</dd></div>
        <div><dt>Revision</dt><dd>{section.revision}</dd></div>
        <div><dt>Words</dt><dd>{section.words.toLocaleString()}</dd></div>
        {section.citations !== undefined && (
          <div><dt>Citations</dt><dd>{section.citations.resolved} resolved{section.citations.needingReview > 0 ? ` · ${section.citations.needingReview} needs review` : ""}</dd></div>
        )}
      </dl>
      {section.issues.length > 0 && (
        <section className="readiness-quick__issues" aria-labelledby="readiness-quick-issues">
          <h3 id="readiness-quick-issues">Known issues</h3>
          <ul>{section.issues.map((issue) => <li key={issue.id}>{issue.title}</li>)}</ul>
        </section>
      )}
      <article className="readiness-quick__content" aria-label={`${section.title} read-only excerpt`}>
        <p>{section.content.trim() === "" ? "No stored section content yet." : section.content}</p>
      </article>
      <footer>
        {onOpenSection !== undefined && <button type="button" onClick={() => onOpenSection(section)}>Open full section</button>}
        {onOpenEditor !== undefined && <button type="button" onClick={() => onOpenEditor(section)}>Open in editor</button>}
        {onViewHistory !== undefined && <button type="button" onClick={() => onViewHistory(section)}>View history</button>}
      </footer>
    </aside>
  );
}

function SectionRow({
  section,
  expanded,
  onToggle,
  onReview,
}: {
  section: ReadinessSectionView;
  expanded: boolean;
  onToggle: () => void;
  onReview: (opener: HTMLElement) => void;
}) {
  const detailId = `readiness-section-${section.id}`;
  return (
    <tr className={section.issues.length > 0 ? "readiness-row readiness-row--attention" : "readiness-row"}>
      <th scope="row">
        <button type="button" className="readiness-row__toggle" aria-expanded={expanded} aria-controls={detailId} onClick={onToggle}>
          <span>{section.sectionNumber}</span>
          <strong>{section.title}</strong>
        </button>
        <div id={detailId} className={expanded ? "readiness-row__mobile-detail readiness-row__mobile-detail--open" : "readiness-row__mobile-detail"}>
          <span>Revision {section.revision}</span>
          <span>{section.words.toLocaleString()} words</span>
          {section.issues.map((issue) => <em key={issue.id}>{issue.title}</em>)}
        </div>
      </th>
      <td><span className={`readiness-row__status readiness-row__status--${section.status}`}>{section.status === "done" ? "Done" : "Draft"}</span></td>
      <td>{section.revision === 0 ? "—" : `Revision ${section.revision}`}</td>
      <td>{section.words === 0 ? "—" : section.words.toLocaleString()}</td>
      <td>
        {section.citations === undefined
          ? "Not available"
          : section.citations.needingReview > 0
            ? `${section.citations.needingReview} needs review`
            : `${section.citations.resolved} resolved`}
      </td>
      <td>{formatUpdated(section.updatedAt)}</td>
      <td><button type="button" onClick={(event) => onReview(event.currentTarget)}>Review</button></td>
    </tr>
  );
}

/** Page 15 issue queue, fixed-order section table, and adaptive quick review. */
export function ReadinessTable({
  data,
  filter,
  onFilterChange,
  onIssueAction,
  onOpenSection,
  onOpenEditor,
  onViewHistory,
  checking,
}: {
  data: ReadinessView;
  filter: ReadinessFilter;
  onFilterChange: (filter: ReadinessFilter) => void;
  onIssueAction?: (issue: ReadinessIssueView) => void;
  onOpenSection?: (section: ReadinessSectionView) => void;
  onOpenEditor?: (section: ReadinessSectionView) => void;
  onViewHistory?: (section: ReadinessSectionView) => void;
  checking?: boolean;
}) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [selected, setSelected] = useState<ReadinessSectionView | null>(null);
  const [opener, setOpener] = useState<HTMLElement | null>(null);
  const visible = data.sections.filter((section) => {
    if (filter === "draft") return section.status === "draft";
    if (filter === "done") return section.status === "done";
    if (filter === "attention") return section.issues.length > 0;
    return true;
  });
  return (
    <>
      <IssueList issues={data.issues} onAction={onIssueAction} checking={checking} />
      <section className="readiness-sections" aria-labelledby="readiness-sections-title">
        <div className="readiness-sections__header">
          <h2 id="readiness-sections-title">ICH M11 protocol sections</h2>
          <div className="readiness-filters" aria-label="Section filters">
            {([
              ["all", "All sections"],
              ["draft", "Draft"],
              ["done", "Done"],
              ["attention", "Needs attention"],
            ] as const).map(([value, label]) => (
              <button key={value} type="button" aria-pressed={filter === value} onClick={() => onFilterChange(value)}>
                {label}
              </button>
            ))}
          </div>
        </div>
        {visible.length === 0 ? (
          <div className="readiness-sections__empty" role="status">
            <p>No sections match this filter.</p>
            <button type="button" onClick={() => onFilterChange("all")}>Show all sections</button>
          </div>
        ) : (
          <div className="readiness-table-wrap">
            <table className="readiness-table">
              <thead><tr><th>Section</th><th>Status</th><th>Revision</th><th>Words</th><th>Citations</th><th>Updated</th><th>Action</th></tr></thead>
              <tbody>
                {visible.map((section) => (
                  <SectionRow
                    key={section.id}
                    section={section}
                    expanded={expanded.has(section.id)}
                    onToggle={() => setExpanded((current) => {
                      const next = new Set(current);
                      if (next.has(section.id)) next.delete(section.id);
                      else next.add(section.id);
                      return next;
                    })}
                    onReview={(button) => { setOpener(button); setSelected(section); }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {selected !== null && (
        <QuickReview
          section={selected}
          returnFocusTo={opener}
          onClose={() => setSelected(null)}
          onOpenSection={onOpenSection}
          onOpenEditor={onOpenEditor}
          onViewHistory={onViewHistory}
        />
      )}
    </>
  );
}
