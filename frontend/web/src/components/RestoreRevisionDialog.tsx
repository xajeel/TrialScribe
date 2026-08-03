import { useEffect, useId, useRef } from "react";

import type { RevisionRowView } from "../product/governanceReviewFixtures";

const FOCUSABLE =
  'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Focus-safe, review-only demonstration of a future immutable restore contract. */
export function RestoreRevisionDialog({
  open,
  revision,
  newRevisionNumber,
  pending = false,
  returnFocusTo,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  revision: RevisionRowView;
  newRevisionNumber: number;
  pending?: boolean;
  returnFocusTo: HTMLElement | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pending) {
        event.stopPropagation();
        onCancel();
        return;
      }
      if (event.key !== "Tab" || panelRef.current === null) return;
      const targets = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (targets.length === 0) return;
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onCancel, open, pending]);

  useEffect(() => {
    if (open) {
      wasOpen.current = true;
      return;
    }
    if (!wasOpen.current) return;
    wasOpen.current = false;
    returnFocusTo?.focus();
  }, [open, returnFocusTo]);

  if (!open) return null;

  return (
    <div className="restore-dialog" role="presentation">
      <div
        ref={panelRef}
        className="restore-dialog__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <p className="restore-dialog__eyebrow">Review demonstration</p>
        <h2 id={titleId}>Restore revision {revision.revisionNumber}?</h2>
        <p id={descriptionId}>
          Revision {revision.revisionNumber} will be shown as copied into new revision {newRevisionNumber}. Existing history remains unchanged, and no stored content changes in this demonstration.
        </p>
        <dl className="restore-dialog__facts">
          <div><dt>Source revision</dt><dd>{revision.revisionNumber}</dd></div>
          <div><dt>New revision</dt><dd>{newRevisionNumber}</dd></div>
          <div><dt>Section status after restore</dt><dd>Draft</dd></div>
          <div><dt>Restored content</dt><dd>{revision.words.toLocaleString()} words{revision.sourceSummary === undefined ? "" : ` · ${revision.sourceSummary}`}</dd></div>
        </dl>
        <div className="restore-dialog__actions">
          <button type="button" disabled={pending} onClick={onCancel}>Cancel</button>
          <button
            ref={confirmRef}
            type="button"
            className="restore-dialog__confirm"
            disabled={pending}
            onClick={onConfirm}
          >
            {pending ? "Restoring revision…" : `Restore as revision ${newRevisionNumber}`}
          </button>
        </div>
      </div>
    </div>
  );
}
