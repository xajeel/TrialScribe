import { useEffect, useId, useRef } from "react";

import type { M11Section } from "../api/types";

/** Native modal presenting a complete M11 section without leaving the workspace. */
export function SectionModal({
  section,
  returnFocusTo,
  onClose,
}: {
  section: M11Section | null;
  returnFocusTo: HTMLElement | null;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (section === null) {
      return;
    }
    const dialog = dialogRef.current;
    if (dialog === null) {
      return;
    }

    if (!dialog.open) {
      if (typeof dialog.showModal === "function") {
        dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }
    }
    closeRef.current?.focus();

    return () => {
      if (dialog.open) {
        if (typeof dialog.close === "function") {
          dialog.close();
        } else {
          dialog.removeAttribute("open");
        }
      }
      returnFocusTo?.focus();
    };
  }, [returnFocusTo, section]);

  if (section === null) {
    return null;
  }

  return (
    <dialog
      ref={dialogRef}
      className="section-modal"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
    >
      <div className="section-modal__header">
        <div>
          <p className="workspace-pane__eyebrow">
            Section {section.section_number}
          </p>
          <h2 id={titleId}>{section.title}</h2>
        </div>
        <button
          ref={closeRef}
          type="button"
          className="button button--ghost"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <div className="section-modal__content">
        <section aria-labelledby={`${titleId}-instructions`}>
          <h3 id={`${titleId}-instructions`}>Instructions</h3>
          <p>{section.instructions || "No section instructions yet."}</p>
        </section>
        <section aria-labelledby={`${titleId}-content`}>
          <h3 id={`${titleId}-content`}>Full section content</h3>
          <div className="section-modal__prose">
            {section.content || "This section has no content yet."}
          </div>
        </section>
      </div>
    </dialog>
  );
}
