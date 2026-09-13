import { useEffect, useId, useRef } from "react";

import type { RevisionRowView } from "../product/governanceReviewFixtures";

function formatPreviewDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/** Read-only Page 14 snapshot detail; restore is absent unless explicitly supplied. */
export function RevisionPreview({
  revision,
  returnFocusTo,
  onClose,
  onCompare,
  onRestore,
}: {
  revision: RevisionRowView | null;
  returnFocusTo: HTMLElement | null;
  onClose: () => void;
  onCompare?: (revision: RevisionRowView) => void;
  onRestore?: (revision: RevisionRowView, opener: HTMLElement) => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (revision === null) {
      return;
    }
    closeRef.current?.focus();
    return () => returnFocusTo?.focus();
  }, [returnFocusTo, revision]);

  if (revision === null) {
    return null;
  }

  return (
    <aside className="revision-preview" aria-labelledby={titleId}>
      <header className="revision-preview__header">
        <div>
          <p>Revision preview</p>
          <h2 id={titleId}>Revision {revision.revisionNumber}</h2>
          <span>{revision.actionLabel}</span>
        </div>
        <button ref={closeRef} type="button" onClick={onClose} aria-label="Close revision preview">
          ×
        </button>
      </header>
      <dl className="revision-preview__metadata">
        <div><dt>Author</dt><dd>{revision.authorLabel}</dd></div>
        <div><dt>Date</dt><dd>{formatPreviewDate(revision.createdAt)}</dd></div>
        <div><dt>Status</dt><dd>{revision.status === "done" ? "Done" : "Draft"}</dd></div>
        <div><dt>Word count</dt><dd>{revision.words.toLocaleString()}</dd></div>
        {revision.sourceSummary !== undefined && (
          <div><dt>Sources</dt><dd>{revision.sourceSummary}</dd></div>
        )}
      </dl>
      <article className="revision-preview__content" aria-label={`Revision ${revision.revisionNumber} section text`}>
        <p className="revision-preview__content-label">Read-only section text</p>
        <p>{revision.content}</p>
      </article>
      <footer className="revision-preview__footer">
        <p>Restoring creates a new revision. Existing history remains unchanged.</p>
        <div>
          {onCompare !== undefined && (
            <button type="button" onClick={() => onCompare(revision)}>Compare with current</button>
          )}
          {onRestore !== undefined && (
            <button
              type="button"
              className="revision-preview__restore"
              onClick={(event) => onRestore(revision, event.currentTarget)}
            >
              Restore as new revision
            </button>
          )}
        </div>
      </footer>
    </aside>
  );
}
