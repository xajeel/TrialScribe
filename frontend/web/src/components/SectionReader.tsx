import { useEffect, useId, useRef, useState } from "react";

import { listEvidenceChunks } from "../api/evidence";
import type { EvidenceChunkRecord, M11Section } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import { splitCitedText } from "../citations/citeMarkers";
import { CitationInspector } from "./CitationInspector";
import { CitedSectionText } from "./CitedSectionText";

/** Word count over the stored content, used for the reader's details list. */
export function wordCountOf(content: string): number {
  const trimmed = content.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

function CompletedOn({ isoDate }: { isoDate: string }) {
  const parsed = new Date(isoDate);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return (
    <p className="section-reader__locked-when">
      Marked done on{" "}
      {parsed.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })}
      .
    </p>
  );
}

/**
 * Reads one M11 section in the state the data puts it in: an empty section
 * offers the two actions that start it, a done section is read-only, and a
 * draft shows its instructions alongside the prose.
 */
export function SectionReader({
  section,
  returnFocusTo,
  onOpenInEditor,
  onAddInstruction,
  onClose,
  inspectCitations,
}: {
  section: M11Section | null;
  returnFocusTo: HTMLElement | null;
  onOpenInEditor: (section: M11Section) => void;
  onAddInstruction: (section: M11Section) => void;
  onClose: () => void;
  inspectCitations?: {
    fetcher: AuthorizedFetch;
    organizationId: string;
    conversationId: string;
  };
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const [citationOpen, setCitationOpen] = useState(false);
  const [citation, setCitation] = useState<EvidenceChunkRecord | null>(null);
  const [citationMissing, setCitationMissing] = useState(false);

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

    // Dismissal is reported through onCancel (Escape) and the Close button
    // only. The element's own `close` event is deliberately not wired: it also
    // fires when an effect re-run closes the dialog, which would report a
    // teardown as a user dismissal and unmount the reader on mount.
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

  useEffect(() => {
    setCitationOpen(false);
    setCitation(null);
    setCitationMissing(false);
  }, [section?.id]);

  if (section === null) {
    return null;
  }

  const done = section.status === "done";
  const empty = section.content.trim() === "";
  const words = wordCountOf(section.content);
  const clickableCitations =
    inspectCitations !== undefined &&
    splitCitedText(section.content).some((part) => part.type === "cite");

  async function inspectCitation(id: string) {
    if (inspectCitations === undefined) {
      return;
    }
    setCitationOpen(true);
    setCitation(null);
    setCitationMissing(false);
    try {
      const page = await listEvidenceChunks(
        inspectCitations.fetcher,
        inspectCitations.organizationId,
        inspectCitations.conversationId,
        [id],
      );
      const chunk = page.items[0] ?? null;
      setCitation(chunk);
      setCitationMissing(chunk === null);
    } catch {
      setCitation(null);
      setCitationMissing(true);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="section-reader"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="section-reader__header">
        <div className="section-reader__identity">
          <p className="section-reader__eyebrow">
            Section {section.section_number}
          </p>
          <h2 id={titleId}>{section.title}</h2>
          <span
            className={
              done
                ? "section-reader__badge section-reader__badge--done"
                : "section-reader__badge"
            }
          >
            {done ? "Done" : "Draft"}
          </span>
        </div>
        <div className="section-reader__header-actions">
          {!done && (
            <button
              type="button"
              className="section-reader__primary"
              onClick={() => onOpenInEditor(section)}
            >
              Open in editor
            </button>
          )}
          <button
            ref={closeRef}
            type="button"
            className="section-reader__close"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>

      <div className="section-reader__body">
        <div className="section-reader__main">
          {done && (
            <div className="section-reader__locked">
              <p className="section-reader__locked-title">Read only</p>
              <p>
                This section is marked done. Reopen it from the editor to make
                further changes.
              </p>
              {section.completed_at !== null && (
                <CompletedOn isoDate={section.completed_at} />
              )}
            </div>
          )}

          {!done && section.instructions.trim() !== "" && (
            <section
              className="section-reader__instructions"
              aria-labelledby={`${titleId}-instructions`}
            >
              <h3 id={`${titleId}-instructions`}>Section instructions</h3>
              <p>{section.instructions}</p>
            </section>
          )}

          {empty ? (
            <div className="section-reader__empty">
              <h3>No content available</h3>
              <p>
                This section has no content yet. Open the editor to write it, or
                add an instruction describing what it should cover.
              </p>
              <div className="section-reader__empty-actions">
                <button
                  type="button"
                  className="section-reader__primary"
                  onClick={() => onOpenInEditor(section)}
                >
                  Open in editor
                </button>
                <button
                  type="button"
                  className="section-reader__secondary"
                  onClick={() => onAddInstruction(section)}
                >
                  Add instruction
                </button>
              </div>
            </div>
          ) : (
            <article
              className="section-reader__prose"
              aria-label={`${section.title} content`}
            >
              {clickableCitations ? (
                <CitedSectionText
                  content={section.content}
                  onInspect={(id) => void inspectCitation(id)}
                />
              ) : (
                section.content
              )}
            </article>
          )}
        </div>

        {citationOpen && (
          <CitationInspector
            chunk={citation}
            missing={citationMissing}
            onClose={() => {
              setCitationOpen(false);
              setCitation(null);
              setCitationMissing(false);
            }}
          />
        )}

        <aside
          className="section-reader__details"
          aria-labelledby={`${titleId}-details`}
        >
          <h3 id={`${titleId}-details`}>Section details</h3>
          <dl>
            <div>
              <dt>Status</dt>
              <dd>{done ? "Done" : "Draft"}</dd>
            </div>
            <div>
              <dt>Revision</dt>
              <dd>{section.current_revision}</dd>
            </div>
            <div>
              <dt>Catalog</dt>
              <dd>{section.catalog_version}</dd>
            </div>
            <div>
              <dt>Word count</dt>
              <dd>{words.toLocaleString()}</dd>
            </div>
          </dl>
        </aside>
      </div>
    </dialog>
  );
}
